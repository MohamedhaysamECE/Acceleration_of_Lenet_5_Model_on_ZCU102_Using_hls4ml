"""
run_hls4ml_100images.py

Same flow as run_hls4ml.py + generate_tb_data.py, but for 100 images
instead of 1, so hls4ml's own cosim (RTL co-simulation) runs against
all 100 samples instead of just IMAGE_INDEX 0.

WHAT THIS DOES (identical structure to your two existing scripts):
  1. Loads the QKeras model, builds the hls4ml config -- byte-for-byte
     the same as run_hls4ml.py (same precisions, Strategy, ReuseFactor).
  2. Converts + compiles the hls4ml model.
  3. Writes tb_data/tb_input_features.dat and
     tb_data/tb_output_predictions.dat for the FIRST 100 MNIST test
     images (IMAGE_INDICES = 0..99), in the exact same format as your
     generate_tb_data.py:
       - tb_input_features.dat  : 100 lines, 784 space-separated
         NORMALIZED FLOATS each (NOT pre-quantized -- myproject_test.cpp
         assigns these into the ap_fixed input port, which performs
         the fixed-point cast for you, exactly as before).
       - tb_output_predictions.dat : 100 lines, 10 space-separated
         Keras float softmax values each (used by hls4ml to report
         Keras/HLS agreement during cosim).
  4. Calls hls_model.build(csim=True, synth=True, cosim=True,
     export=True, vsynth=False) -- exactly the same build call as
     run_hls4ml.py, just now cosim will run over 100 samples instead
     of 1.

WARNING: cosim time scales roughly linearly with the number of
samples. If a single-image cosim took N minutes, 100 images will
take roughly 100x that. Consider trying IMAGE_INDICES = list(range(10))
first as a smoke test before committing to the full 100.

Run this from the same directory as your existing run_hls4ml.py
(needs lenet_pruned50_qkeras.h5 next to it).
"""

import os
import numpy as np
import tensorflow as tf
import hls4ml
from tensorflow_model_optimization.python.core.sparsity.keras import pruning_wrapper
from tensorflow_model_optimization.sparsity.keras import strip_pruning
from qkeras.utils import _add_supported_quantized_objects

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
MODEL_PATH     = "lenet_pruned50_qkeras.h5"
HLS_OUTPUT_DIR = "lenet5_hls_100"          # same output_dir as run_hls4ml.py
N_IMAGES       = 100
IMAGE_INDICES  = list(range(N_IMAGES))  # 0..99, matches sim_input_images.hex ordering
TB_DATA_DIR    = os.path.join(HLS_OUTPUT_DIR, "tb_data")

# ---------------------------------------------------------------------
# 1) Load the QKeras model - identical to run_hls4ml.py
# ---------------------------------------------------------------------
co = {}
_add_supported_quantized_objects(co)
co['PruneLowMagnitude'] = pruning_wrapper.PruneLowMagnitude

keras_model = tf.keras.models.load_model(MODEL_PATH, custom_objects=co)
keras_model = strip_pruning(keras_model)

# ---------------------------------------------------------------------
# 2) Build the hls4ml config - identical to run_hls4ml.py
# ---------------------------------------------------------------------
config = hls4ml.utils.config_from_keras_model(
    keras_model,
    granularity="name",
    backend="Vitis",
    default_precision='ap_fixed<16,6>'
)
config['Model']['Strategy'] = 'Resource'

for layer_name, layer_cfg in config.get('LayerName', {}).items():
    if 'Strategy' in layer_cfg:
        layer_cfg['Strategy'] = 'Resource'

config['LayerName']['q_dense_2']['Precision']['result'] = 'fixed<16,6,RND,SAT>'
config['LayerName']['activation']['exp_table_t'] = 'ap_fixed<18,8>'
config['LayerName']['activation']['inv_table_t'] = 'ap_fixed<18,4>'

config['LayerName']['q_dense']['ReuseFactor'] = 64
config['LayerName']['q_dense_1']['ReuseFactor'] = 90
config['LayerName']['q_dense_2']['ReuseFactor'] = 1

# ---------------------------------------------------------------------
# 3) Convert + compile - identical to run_hls4ml.py
# ---------------------------------------------------------------------
hls_model = hls4ml.converters.convert_from_keras_model(
    model=keras_model,
    hls_config=config,
    backend="Vitis",
    output_dir=HLS_OUTPUT_DIR,
    part="xczu9eg-ffvb1156-2-e",
    io_type='io_stream',
)

print("Compiling...")
hls_model.compile()
print("Compiling done")

# ---------------------------------------------------------------------
# 4) Write tb_data/tb_input_features.dat + tb_output_predictions.dat
#    for 100 images - identical format/logic to generate_tb_data.py,
#    just with IMAGE_INDICES = 0..99 instead of [0].
# ---------------------------------------------------------------------
(_, _), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

x = x_test[IMAGE_INDICES].astype(np.float32) / 255.0
x = x.reshape(len(IMAGE_INDICES), 28, 28, 1)
y_true = y_test[IMAGE_INDICES]

# Flatten each image in row-major (C) order -> shape (N, 784)
x_flat = x.reshape(len(IMAGE_INDICES), -1)

# Reference predictions from the floating-point Keras model (same as
# generate_tb_data.py -- used for the Keras/HLS agreement report)
keras_pred = keras_model.predict(x, verbose=0)

os.makedirs(TB_DATA_DIR, exist_ok=True)

input_path = os.path.join(TB_DATA_DIR, "tb_input_features.dat")
with open(input_path, "w") as f:
    for row in x_flat:
        f.write(" ".join(f"{v:.8f}" for v in row) + "\n")

pred_path = os.path.join(TB_DATA_DIR, "tb_output_predictions.dat")
with open(pred_path, "w") as f:
    for row in keras_pred:
        f.write(" ".join(f"{v:.8f}" for v in row) + "\n")

print(f"Wrote {len(IMAGE_INDICES)} sample(s) to {TB_DATA_DIR}/:")
print("  tb_input_features.dat")
print("  tb_output_predictions.dat")
print(f"True labels: {y_true.tolist()}")
print(f"Keras predicted labels: {np.argmax(keras_pred, axis=1).tolist()}")

# ---------------------------------------------------------------------
# 5) Build + csim/synth/cosim/export - identical call to run_hls4ml.py.
#    This is what actually runs the RTL cosim over all 100 samples.
# ---------------------------------------------------------------------
hls_model.build(csim=True, synth=True, cosim=True, export=True, vsynth=False)
