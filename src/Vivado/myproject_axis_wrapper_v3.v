// ============================================================================
// myproject_axis_wrapper.v  (v3 - hardware-controllable ap_start/ap_ready
//                             batch handshake, driven from the PS via GPIO)
//
// *** WHY THIS VERSION EXISTS ***
// Tying ap_start permanently high (the earlier approach) does NOT reproduce
// the ap_start/ap_ready handshake this core actually needs -- confirmed
// broken both in RTL simulation and on the FPGA. The handshake that WAS
// proven to work is the one in tb_myproject_axis_wrapper_100images_v2.v /
// myproject_autotb.v's start_process:
//     - ap_start is asserted ONCE per batch and held high.
//     - It is deasserted only after N pulses of ap_ready have been
//       observed (one pulse per accepted image/frame).
// This file reproduces that exact handshake as a small hardware FSM, since
// counting ap_ready pulses at ap_clk speed is not something the PS can do
// by polling a register -- it has to happen in fabric.
//
// ap_start / ap_ready / ap_done / ap_idle are now entirely INTERNAL to this
// wrapper (no longer top-level ports). The new top-level control ports,
// meant to be driven from the PS via AXI GPIO:
//
//   start_trigger    : pulse (or level -- only the RISING EDGE matters)
//                       from the PS to begin a new batch of
//                       `num_transactions` images. Only has effect while
//                       the FSM is idle (i.e. after batch_done was seen
//                       for the previous batch, or on the very first run
//                       after reset).
//   num_transactions : how many images the upcoming batch will contain
//                       (e.g. 100, matching NUM_IMAGES in test_data.h).
//                       Must be written by the host BEFORE pulsing
//                       start_trigger. Do not change it mid-batch.
//   batch_done        : goes high and STAYS high once the FSM has
//                       deasserted ap_start after observing
//                       num_transactions ap_ready pulses, until the next
//                       start_trigger rising edge. Lets the host confirm
//                       the hardware-side handshake actually completed,
//                       independent of what the DMA transfer-complete
//                       polling already reports.
// ============================================================================
module myproject_axis_wrapper (
    input  wire          ap_clk,
    input  wire          ap_rst_n,

    // Input side — from AXI DMA MM2S
    input  wire [15:0]   s_axis_tdata,
    input  wire          s_axis_tvalid,
    output wire          s_axis_tready,

    // Output side — to AXI4-Stream Width Converter
    output wire [159:0]  m_axis_tdata,
    output wire          m_axis_tvalid,
    input  wire          m_axis_tready,
    output wire          m_axis_tlast,

    // Batch control — driven from the PS via AXI GPIO
    input  wire          start_trigger,
    input  wire [15:0]   num_transactions,
    output wire          batch_done,

    // Debug / verification taps — purely observational, not used by the PS.
    // Mirror the hls4ml core's internal ap_ctrl signals so a testbench can
    // still see per-transaction start/done/ready/idle pulses even though
    // the batch FSM now owns ap_start. Safe to leave unconnected in
    // synthesis/integration; they don't feed back into any logic.
    output wire          ap_start_dbg,
    output wire          ap_done_dbg,
    output wire          ap_ready_dbg,
    output wire          ap_idle_dbg
);

    // ---- internal ap_ctrl signals to/from the hls4ml core ----
    wire        ap_start;
    wire        ap_done;
    wire        ap_ready;
    wire        ap_idle;

    // ------------------------------------------------------------------
    // ap_start / ap_ready batch controller
    // Direct hardware translation of myproject_autotb.v's start_process:
    // assert ap_start once, hold it through `num_transactions` ap_ready
    // pulses, then drop it and flag batch_done.
    // ------------------------------------------------------------------
    localparam IDLE = 1'b0, RUNNING = 1'b1;

    reg        state;
    reg [15:0] ready_cnt;
    reg        ap_start_reg;
    reg        batch_done_reg;
    reg        start_trigger_d;

    always @(posedge ap_clk or negedge ap_rst_n) begin
        if (!ap_rst_n) begin
            state           <= IDLE;
            ready_cnt       <= 16'd0;
            ap_start_reg    <= 1'b0;
            batch_done_reg  <= 1'b0;
            start_trigger_d <= 1'b0;
        end else begin
            start_trigger_d <= start_trigger;
            case (state)
                IDLE: begin
                    // rising edge on start_trigger, only while idle
                    if (start_trigger && !start_trigger_d) begin
                        ap_start_reg   <= 1'b1;
                        ready_cnt      <= 16'd0;
                        batch_done_reg <= 1'b0;
                        state          <= RUNNING;
                    end
                end
                RUNNING: begin
                    if (ap_ready) begin
                        if ((ready_cnt + 16'd1) >= num_transactions) begin
                            ap_start_reg   <= 1'b0;
                            batch_done_reg <= 1'b1;
                            state          <= IDLE;
                        end else begin
                            ready_cnt <= ready_cnt + 16'd1;
                        end
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end

    assign ap_start   = ap_start_reg;
    assign batch_done = batch_done_reg;

    assign ap_start_dbg = ap_start;
    assign ap_done_dbg  = ap_done;
    assign ap_ready_dbg = ap_ready;
    assign ap_idle_dbg  = ap_idle;

    // ---- hls4ml core instance ----
    myproject u_myproject (
        .ap_clk                (ap_clk),
        .ap_rst_n              (ap_rst_n),
        .q_conv2d_input_TDATA  (s_axis_tdata),
        .q_conv2d_input_TVALID (s_axis_tvalid),
        .q_conv2d_input_TREADY (s_axis_tready),
        .layer19_out_TDATA     (m_axis_tdata),
        .layer19_out_TVALID    (m_axis_tvalid),
        .layer19_out_TREADY    (m_axis_tready),
        .ap_start              (ap_start),
        .ap_done               (ap_done),
        .ap_ready              (ap_ready),
        .ap_idle               (ap_idle)
    );

    assign m_axis_tlast = 1'b1;  // every output beat is a complete, standalone inference result

endmodule
