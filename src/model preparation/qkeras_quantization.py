import tensorflow as tf

from qkeras import (
    QConv2D,
    QDense,
    QActivation,
    quantized_bits
)

(x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

x_train = x_train.astype("float32") / 255.0
x_test = x_test.astype("float32") / 255.0

x_train = x_train[..., tf.newaxis]
x_test = x_test[..., tf.newaxis]

pruned_model = tf.keras.models.load_model(
    "lenet_mnist_pruned50.h5"
)

     qmodel = tf.keras.Sequential([
     QConv2D(
	    filters=6,
	    kernel_size=(5,5),
	    input_shape=(28,28,1),

	    kernel_quantizer=quantized_bits(8,2),
	    bias_quantizer=quantized_bits(8,2)
	),

    QActivation("quantized_relu(8)"),

    tf.keras.layers.AveragePooling2D(pool_size=(2,2)),


    QConv2D(
        filters=16,
        kernel_size=(5,5),

        kernel_quantizer=quantized_bits(8,2),
        bias_quantizer=quantized_bits(8,2)
    ),

    QActivation("quantized_relu(8)"),

    tf.keras.layers.AveragePooling2D(pool_size=(2,2)),


    tf.keras.layers.Flatten(),


    QDense(
        120,
        kernel_quantizer=quantized_bits(8,2),
        bias_quantizer=quantized_bits(8,2)
    ),

    QActivation("quantized_relu(8)"),


    QDense(
        84,
        kernel_quantizer=quantized_bits(8,2),
        bias_quantizer=quantized_bits(8,2)
    ),

    QActivation("quantized_relu(8)"),


    QDense(
        10,
        kernel_quantizer=quantized_bits(8,2),
        bias_quantizer=quantized_bits(8,2)
    ),

    tf.keras.layers.Activation("softmax")

])

qmodel.build((None,28,28,1))


qmodel.summary()

fp_layers = [
    layer for layer in pruned_model.layers
    if len(layer.get_weights()) > 0
]

q_layers = [
    layer for layer in qmodel.layers
    if len(layer.get_weights()) > 0
]

for fp, q in zip(fp_layers, q_layers):
    q.set_weights(fp.get_weights())

print("Weights copied successfully.")

qmodel.compile(

    optimizer="adam",

    loss="sparse_categorical_crossentropy",

    metrics=["accuracy"]

)

qmodel.fit(

    x_train,
    y_train,

    epochs=3,

    batch_size=128,

    validation_split=0.1

)

loss, acc = qmodel.evaluate(x_test, y_test)

print("Accuracy =", acc)

qmodel.save("lenet_pruned50_qkeras.h5")

print("QKeras model saved.")


