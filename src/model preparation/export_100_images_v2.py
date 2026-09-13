"""
export_100_images.py  (v2 - builds hls_model itself, no external session needed)

Builds the SAME hls4ml model (same QKeras source, same config, same
precisions/ReuseFactor/Strategy) as your run_hls4ml.py, compiles it
(no synth/cosim/export -- just enough to call .predict()), and uses
it to export:

  - sim_input_images.hex   : 100 * 784  16-bit hex values (Q6.10,
                              scale=1024), one per line, images
                              concatenated back-to-back. Same
                              quantization as your original
                              single-image script.

  - expected_outputs.hex   : 100 * 10   16-bit hex values, same Q6.10
                              format as the RTL's q_dense_2 output,
                              one per line, per-image blocks of 10.
                              Comes DIRECTLY from hls_model.predict()
                              on the same config that produced your
                              trusted single-image cosim reference --
                              not the plain float Keras model.

  - labels.txt              : true label per image (debug only, not
                              read by the testbench).

Run this from the same directory as run_hls4ml.py (needs the same
lenet_pruned50_qkeras.h5 next to it, or edit MODEL_PATH below).
"""

import os
import numpy as np
import tensorflow as tf
import hls4ml
from tensorflow_model_optimization.python.core.sparsity.keras import pruning_wrapper
from tensorflow_model_optimization.sparsity.keras import strip_pruning
from qkeras.utils import _add_supported_quantized_objects

# ---------------------------------------------------------------------
# Config - export parameters
# ---------------------------------------------------------------------
N_IMAGES   = 100
N_PIXELS   = 784
N_CLASSES  = 10
SCALE      = 1 << 10          # Q6.10, same as your original script
IMG_START  = 0                 # first test-set index to export
MODEL_PATH = "lenet_pruned50_qkeras.h5"
HLS_OUTPUT_DIR = "lenet5_hls"  # same output_dir you used in run_hls4ml.py

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
# 3) Convert + compile (NOT .build() -- we only need .predict(), no
#    synth/cosim/export here, so this stays fast)
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
# 4) Load the 100 MNIST test images - same normalization as run_hls4ml.py
# ---------------------------------------------------------------------
(_, _), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

images_float = x_test[IMG_START:IMG_START + N_IMAGES].astype(np.float32) / 255.0   # (N,28,28)
labels = y_test[IMG_START:IMG_START + N_IMAGES].astype(int)

images_flat = images_float.reshape(N_IMAGES, N_PIXELS)          # for hls_model.predict()
images_chw  = images_float.reshape(N_IMAGES, 28, 28, 1)          # in case predict() wants 4D


def quantize_q6_10(arr_float):
    q = np.round(arr_float * SCALE).astype(np.int32)
    q = np.clip(q, -32768, 32767).astype(np.int16)
    return q


# ---------------------------------------------------------------------
# 5) Write input images (pre-quantized, for the raw Verilog testbench)
# ---------------------------------------------------------------------
with open("sim_input_images.hex", "w") as f:
    for img in images_flat:
        q = quantize_q6_10(img)
        for v in q:
            uv = int(v) & 0xFFFF
            f.write(f"{uv:04x}\n")

print(f"Wrote {N_IMAGES * N_PIXELS} pixel values "
      f"({N_IMAGES} images x {N_PIXELS} pixels) to sim_input_images.hex")

# ---------------------------------------------------------------------
# 6) Write true labels (debug only)
# ---------------------------------------------------------------------
with open("labels.txt", "w") as f:
    for lbl in labels:
        f.write(f"{lbl}\n")
print(f"Wrote {N_IMAGES} true labels to labels.txt")

# ---------------------------------------------------------------------
# 7) Run hls_model.predict() and write expected outputs
# ---------------------------------------------------------------------
try:
    preds = hls_model.predict(images_flat)
except Exception:
    # some hls4ml configs expect the unflattened (N,28,28,1) shape instead
    preds = hls_model.predict(images_chw)

preds = np.asarray(preds).reshape(N_IMAGES, N_CLASSES)

with open("expected_outputs.hex", "w") as f:
    for row in preds:
        q = quantize_q6_10(row)
        for v in q:
            uv = int(v) & 0xFFFF
            f.write(f"{uv:04x}\n")

print(f"Wrote {N_IMAGES * N_CLASSES} expected output values to expected_outputs.hex")

hls_labels = np.argmax(preds, axis=1)
agreement = np.mean(hls_labels == labels)
print(f"hls_model predicted-label accuracy vs true MNIST labels: {agreement:.4f}")
