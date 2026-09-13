// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2023.1 (64-bit)
// Tool Version Limit: 2023.05
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2023 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================

`timescale 1 ns / 1 ps

`define TV_OUT_layer19_out_TDATA "/home/mohamed/Nile_intern/Tasks/Mobilenet_project/test/lenet_project/lenet5_hls_100/myproject_prj/solution1/sim/tv/rtldatafile/rtl.myproject.autotvout_layer19_out.dat"

`define AUTOTB_TRANSACTION_NUM 100

module AESL_axi_s_layer19_out (
    input clk,
    input reset,
    input [160 - 1:0] TRAN_layer19_out_TDATA,
    input TRAN_layer19_out_TVALID,
    output TRAN_layer19_out_TREADY,
    input ready,
    input done,
    output [31:0] transaction);

    wire TRAN_layer19_out_TVALID_temp;
    wire layer19_out_TDATA_full;
    wire layer19_out_TDATA_empty;
    reg layer19_out_TDATA_write_en;
    reg [160 - 1:0] layer19_out_TDATA_write_data;
    reg layer19_out_TDATA_read_en;
    wire [160 - 1:0] layer19_out_TDATA_read_data;
    
    fifo #(1, 160) fifo_layer19_out_TDATA (
        .reset(1'b0),
        .write_clock(clk),
        .write_en(layer19_out_TDATA_write_en),
        .write_data(layer19_out_TDATA_write_data),
        .read_clock(clk),
        .read_en(layer19_out_TDATA_read_en),
        .read_data(layer19_out_TDATA_read_data),
        .full(layer19_out_TDATA_full),
        .empty(layer19_out_TDATA_empty));
    
    always @ (*) begin
        layer19_out_TDATA_write_en <= TRAN_layer19_out_TVALID;
        layer19_out_TDATA_write_data <= TRAN_layer19_out_TDATA;
        layer19_out_TDATA_read_en <= 0;
    end
    assign TRAN_layer19_out_TVALID = TRAN_layer19_out_TVALID_temp;

    
    assign TRAN_layer19_out_TREADY = ~(layer19_out_TDATA_full);
    
    function is_blank_char(input [7:0] in_char);
        if (in_char == " " || in_char == "\011" || in_char == "\012" || in_char == "\015") begin
            is_blank_char = 1;
        end else begin
            is_blank_char = 0;
        end
    endfunction
    
    function [343:0] read_token(input integer fp);
        integer ret;
        begin
            read_token = "";
                    ret = 0;
                    ret = $fscanf(fp,"%s",read_token);
        end
    endfunction
    
    function [343:0] rm_0x(input [343:0] token);
        reg [343:0] token_tmp;
        integer i;
        begin
            token_tmp = "";
            for (i = 0; token[15:0] != "0x"; token = token >> 8) begin
                token_tmp = (token[7:0] << (8 * i)) | token_tmp;
                i = i + 1;
            end
            rm_0x = token_tmp;
        end
    endfunction
    
    reg done_1;
    
    always @ (posedge clk or reset) begin
        if (~reset) begin
            done_1 <= 0;
        end else begin
            done_1 <= done;
        end
    end
    
    reg [31:0] transaction_save_layer19_out_TDATA;
    
    assign transaction = transaction_save_layer19_out_TDATA;
    
    initial begin : AXI_stream_receiver_layer19_out_TDATA
        integer fp;
        reg [160 - 1:0] data;
        reg [8 * 5:1] str;
        
        transaction_save_layer19_out_TDATA = 0;
        fifo_layer19_out_TDATA.clear();
        wait (reset === 1);
        forever begin
            @ (negedge clk);
            if (done_1 == 1) begin
                fp = $fopen(`TV_OUT_layer19_out_TDATA, "a");
                if (fp == 0) begin // Failed to open file
                    $display("ERROR: Failed to open file \"%s\"!", `TV_OUT_layer19_out_TDATA);
                    $finish;
                end
                $fdisplay(fp, "[[transaction]] %d", transaction_save_layer19_out_TDATA);
                while (~fifo_layer19_out_TDATA.empty) begin
                    fifo_layer19_out_TDATA.pop(data);
                    $fdisplay(fp, "0x%x", data);
                end
                $fdisplay(fp, "[[/transaction]]");
                transaction_save_layer19_out_TDATA = transaction_save_layer19_out_TDATA + 1;
                fifo_layer19_out_TDATA.clear();
                $fclose(fp);
            end
        end
    end

endmodule
