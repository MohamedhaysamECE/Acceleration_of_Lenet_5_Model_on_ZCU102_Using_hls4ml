/*
 * LeNet-5 HW Inference — ZCU102 + AXI4-Stream FIFOs + GPIO
 * Measures Latency, Throughput, and Accuracy.
 */

#include "xparameters.h"
#include "xil_printf.h"
#include "xil_io.h"
#include "xstatus.h"
#include "sleep.h"
#include "xtime_l.h"   // For Zynq UltraScale+ Global Timer
#include "test_data.h" // Includes images and labels

/* ── Base Addresses (Must match Vivado Address Editor) ── */
#define TX_FIFO_BASE      0xA0000000UL
#define RX_FIFO_BASE      0xA0010000UL
#define GPIO_CTRL_BASE    0xA0020000UL  // Ch1=num_transactions, Ch2=start_trigger
#define GPIO_STATUS_BASE  0xA0030000UL  // Ch1=batch_done

/* ── PG080 Register Offsets ── */
#define FIFO_ISR   0x00   /* Interrupt Status Reg  (W1C) */
#define FIFO_IER   0x04   /* Interrupt Enable Reg        */
#define FIFO_TDFV  0x0C   /* TX FIFO Vacancy (words)     */
#define FIFO_TDFD  0x10   /* TX Data Write Port          */
#define FIFO_TLR   0x14   /* TX Length Reg -> TRIGGER    */
#define FIFO_RDFO  0x1C   /* RX FIFO Occupancy (words)   */
#define FIFO_RDFD  0x20   /* RX Data Read Port           */
#define FIFO_RLR   0x24   /* RX Length Reg -> UNLOCKS RX */

#define ISR_TC     0x08000000UL   /* bit[27] TX Complete */
#define ISR_CLEAR  0xFFFFFFFFUL

/* ── Data Sizes ── */
#define WORDS_PER_IMG    (IMG_PIXELS / 2)                  /* 392 32-bit words */
#define TX_BYTES_TOTAL   (NUM_IMAGES * WORDS_PER_IMG * 4)  /* Total TX payload */
#define LOGITS           10
#define OUT_WORDS        5                                 /* 5x 32-bit words = 160 bits */
#define RX_WORDS_TOTAL   (NUM_IMAGES * OUT_WORDS)

/* ── Helpers ── */
#define WR(base, off, val)  Xil_Out32((base) + (off), (val))
#define RD(base, off)       Xil_In32((base)  + (off))

/* ── Prototypes ── */
static int  init_hw(void);
static void start_wrapper(void);
static int  tx_all_images(void);
static int  rx_all_results(int16_t out[NUM_IMAGES][LOGITS]);
static int  argmax16(const int16_t *a, int n);

/* ═══════════════════════════════════════════════════════════════════ */
int main(void)
{
    int16_t results[NUM_IMAGES][LOGITS];
    XTime t_start, t_end;
    double elapsed_ms, throughput, latency_per_img;

    xil_printf("\r\n================================================\r\n");
    xil_printf("  LeNet-5 ZCU102 Inference (FIFO + GPIO) \r\n");
    xil_printf("================================================\r\n");

    /* 1. Initialize Hardware */
    if (init_hw() != XST_SUCCESS) {
        xil_printf("Hardware Initialization Failed!\r\n");
        return XST_FAILURE;
    }

    /* WAIT FOR USER TO ARM ILA */
    xil_printf("\r\n================================================\r\n");
    xil_printf("[!] PAUSING FOR 60 SECONDS.\r\n");
    xil_printf("[!] GO TO VIVADO -> AUTO CONNECT -> ARM ILA TRIGGER NOW!\r\n");
    xil_printf("================================================\r\n");
    for (int s = 15; s > 0; s--) {
        if (s % 5 == 0 || s <= 10) {
            xil_printf("... Starting in %d seconds ...\r\n", s);
        }
        sleep(1);
    }
    xil_printf("[!] RESUMING EXECUTION!\r\n\r\n");

    /* 2. Configure Wrapper */
    xil_printf("[DBG] Writing num_transactions=%d to GPIO...\r\n", NUM_IMAGES);
    WR(GPIO_CTRL_BASE, 0x00, NUM_IMAGES);
    xil_printf("[DBG] GPIO readback = %lu\r\n", RD(GPIO_CTRL_BASE, 0x00));
    xil_printf("[DBG] TX FIFO ISR=0x%08lx TDFV=%lu\r\n",
               RD(TX_FIFO_BASE, FIFO_ISR), RD(TX_FIFO_BASE, FIFO_TDFV));
    xil_printf("[DBG] RX FIFO ISR=0x%08lx RDFO=%lu\r\n",
               RD(RX_FIFO_BASE, FIFO_ISR), RD(RX_FIFO_BASE, FIFO_RDFO));

    /* Take Start Timestamp */
    XTime_GetTime(&t_start);

    /* 3. Pulse start_trigger */
    xil_printf("[DBG] Pulsing start_trigger...\r\n");
    start_wrapper();
    xil_printf("[DBG] start_trigger done. Starting TX...\r\n");

    if (tx_all_images() != XST_SUCCESS) return XST_FAILURE;

    /* 4. Wait for batch_done from GPIO */
    xil_printf("[*] Waiting for batch_done from FPGA...\r\n");
    u32 timeout = 0;
    while ((RD(GPIO_STATUS_BASE, 0x00) & 0x1) == 0) { // Check bit 0 of status GPIO
        if (++timeout > 50000000U) {
            xil_printf("ERROR: batch_done timeout!\r\n");
            return XST_FAILURE;
        }
    }

    /* Take End Timestamp */
    XTime_GetTime(&t_end);

    /* 5. Fetch Results */
    if (rx_all_results(results) != XST_SUCCESS) return XST_FAILURE;

    /* 6. Calculate Metrics */
    elapsed_ms = 1000.0 * (double)(t_end - t_start) / (double)COUNTS_PER_SECOND;
    latency_per_img = elapsed_ms / NUM_IMAGES;
    throughput = (NUM_IMAGES / elapsed_ms) * 1000.0;

    int correct = 0;
    for (int i = 0; i < NUM_IMAGES; i++) {
        int pred = argmax16(results[i], LOGITS);
        if (pred == labels[i]) correct++;
    }

    /* 7. Report */
    /* Note: xil_printf does not support %f, so we cast to int for whole numbers
       and compute fractional parts manually */
    int elap_int = (int)elapsed_ms;
    int elap_frac = (int)((elapsed_ms - elap_int) * 1000);

    int lat_int = (int)latency_per_img;
    int lat_frac = (int)((latency_per_img - lat_int) * 1000);

    int fps_int = (int)throughput;
    int acc_int = (int)((correct * 100.0) / NUM_IMAGES);

    xil_printf("\r\n================ PERFORMANCE ===================\r\n");
    xil_printf("  Batch Size      : %d images\r\n", NUM_IMAGES);
    xil_printf("  Total Time      : %d.%03d ms\r\n", elap_int, elap_frac);
    xil_printf("  Latency/Image   : %d.%03d ms\r\n", lat_int, lat_frac);
    xil_printf("  Throughput      : %d FPS (images/sec)\r\n", fps_int);
    xil_printf("  Accuracy        : %d / %d (%d %%)\r\n", correct, NUM_IMAGES, acc_int);
    xil_printf("================================================\r\n\r\n");

    /* Debug: Print Logits for Image 0 to compare with expected_outputs.hex */
    xil_printf("[DEBUG] Logits for Image 0 (Expected vs Actual):\r\n");
    for (int i = 0; i < LOGITS; i++) {
        xil_printf("  Logit[%d] = %d\r\n", i, results[0][i]);
    }
    xil_printf("  -> Predicted Label: %d\r\n", argmax16(results[0], LOGITS));
    xil_printf("  -> True Label     : %d\r\n\r\n", labels[0]);

    return XST_SUCCESS;
}

/* ═══════════════════════════════════════════════════════════════════ */
static int init_hw(void)
{
    /* Clear ISR and disable interrupts */
    WR(TX_FIFO_BASE, FIFO_ISR, ISR_CLEAR);
    if (RD(TX_FIFO_BASE, FIFO_ISR) != 0) return XST_FAILURE;
    WR(RX_FIFO_BASE, FIFO_ISR, ISR_CLEAR);
    if (RD(RX_FIFO_BASE, FIFO_ISR) != 0) return XST_FAILURE;

    /* Enable TC/RC in IER so sticky bits work for polling */
    WR(TX_FIFO_BASE, FIFO_IER, 0x0C000000UL);
    WR(RX_FIFO_BASE, FIFO_IER, 0x0C000000UL);

    /* Configure GPIO Direction: Ctrl=Outputs(0), Status=Input(1) */
    WR(GPIO_CTRL_BASE, 0x04, 0x0);        // Ch1 Dir = Output
    WR(GPIO_CTRL_BASE, 0x0C, 0x0);        // Ch2 Dir = Output
    WR(GPIO_STATUS_BASE, 0x04, 0xFFFFFFFF); // Ch1 Dir = Input

    /* Clear start_trigger initially */
    WR(GPIO_CTRL_BASE, 0x08, 0x0);        // Ch2 = start_trigger

    return XST_SUCCESS;
}

/* ═══════════════════════════════════════════════════════════════════ */
static void start_wrapper(void)
{
    /* Pulse start_trigger on GPIO Ctrl Ch2 bit 0 */
    WR(GPIO_CTRL_BASE, 0x08, 0x1);
    usleep(1);
    WR(GPIO_CTRL_BASE, 0x08, 0x0);
}

/* ═══════════════════════════════════════════════════════════════════
 * tx_all_images — sends 1 image at a time.
 *
 * WHY: TX FIFO is in Store-and-Forward mode. TVALID stays LOW until TLR
 * is written. FIFO depth = 4096 words. Total data = 100×392 = 39,200
 * words. Writing all images before TLR fills the FIFO at ~image #10
 * and hangs forever waiting for TDFV > 0.
 *
 * FIX: Write 392 words for image N, fire TLR (1568 bytes), wait for
 * TX Complete, then repeat for image N+1. Each image is one AXI-Stream
 * packet. The DUT consumes 784 pixels per packet internally, so TLAST
 * between images is harmless.
 * ═══════════════════════════════════════════════════════════════════ */
static int tx_all_images(void)
{
    /* Bytes in one image = 392 words × 4 bytes */
    const u32 IMG_BYTES = WORDS_PER_IMG * 4;  /* 1568 */

    for (int img = 0; img < NUM_IMAGES; img++) {

        /* Clear ISR before each image */
        WR(TX_FIFO_BASE, FIFO_ISR, ISR_CLEAR);

        /* Write 392 words (784 pixels) for this image */
        for (int w = 0; w < WORDS_PER_IMG; w++) {
            u32 word = ((u32)(u16)images[img][2*w+1] << 16)
                     | ((u32)(u16)images[img][2*w]);
            /* Spin if FIFO is full (should never happen for 392 words
               into a 4096-deep FIFO, but guard anyway) */
            while (!RD(TX_FIFO_BASE, FIFO_TDFV)) {}
            WR(TX_FIFO_BASE, FIFO_TDFD, word);
        }

        /* Write TLR → releases this image's pixels onto AXI-Stream */
        xil_printf("[DBG] Img%d: writing TLR=%lu bytes\r\n", img, IMG_BYTES);
        WR(TX_FIFO_BASE, FIFO_TLR, IMG_BYTES);
        xil_printf("[DBG] Img%d: TLR written, polling TC...\r\n", img);

        /* Poll ISR bit[27] (TC = Transmit Complete) */
        u32 to = 0;
        while (!(RD(TX_FIFO_BASE, FIFO_ISR) & ISR_TC)) {
            /* Print ISR every 1M iterations so we can see what's set */
            if (to == 1000000U)
                xil_printf("[DBG] Img%d: TC not set yet, ISR=0x%08lx TDFV=%lu\r\n",
                           img, RD(TX_FIFO_BASE, FIFO_ISR), RD(TX_FIFO_BASE, FIFO_TDFV));
            if (++to > 20000000U) {
                xil_printf("TX timeout at image %d ISR=0x%08lx\r\n",
                           img, RD(TX_FIFO_BASE, FIFO_ISR));
                return XST_FAILURE;
            }
        }
        WR(TX_FIFO_BASE, FIFO_ISR, ISR_TC);
        if (img < 3 || img == 99)
            xil_printf("[DBG] Img%d: TC received OK.\r\n", img);
    }

    xil_printf("[*] All %d images transmitted.\r\n", NUM_IMAGES);
    return XST_SUCCESS;
}

/* ═══════════════════════════════════════════════════════════════════ */
static int rx_all_results(int16_t out[NUM_IMAGES][LOGITS])
{
    /* Wait for results */
    xil_printf("[DBG] Fetching results. Expecting %d words...\r\n", RX_WORDS_TOTAL);
    u32 to = 0;
    u32 rdfo = 0;
    while ((rdfo = RD(RX_FIFO_BASE, FIFO_RDFO)) < (u32)RX_WORDS_TOTAL) {
        if (++to > 100000000U) {
            xil_printf("ERROR: RX timeout! RDFO is stuck at %lu words.\r\n", rdfo);
            return XST_FAILURE;
        }
    }
    xil_printf("[DBG] RX FIFO has %lu words. Reading now...\r\n", rdfo);

    /* Read and unpack */
    for (int img = 0; img < NUM_IMAGES; img++) {
        /* Xilinx AXI-Stream FIFO Requirement: You MUST read RLR to "unlock"
           the packet onto the RDFD register. Without this, RDFD returns 0! */
        u32 rlr = RD(RX_FIFO_BASE, FIFO_RLR);
        if (img == 0) {
            xil_printf("[DBG] Image 0: RLR = %lu bytes\r\n", rlr);
        }

        for (int w = 0; w < OUT_WORDS; w++) {
            u32 word = RD(RX_FIFO_BASE, FIFO_RDFD);
            out[img][2*w]   = (int16_t)(word & 0xFFFF);
            out[img][2*w+1] = (int16_t)(word >> 16);
        }
    }
    WR(RX_FIFO_BASE, FIFO_ISR, ISR_CLEAR);
    return XST_SUCCESS;
}

/* ═══════════════════════════════════════════════════════════════════ */
static int argmax16(const int16_t *a, int n)
{
    int idx = 0;
    for (int i = 1; i < n; i++)
        if (a[i] > a[idx]) idx = i;
    return idx;
}

