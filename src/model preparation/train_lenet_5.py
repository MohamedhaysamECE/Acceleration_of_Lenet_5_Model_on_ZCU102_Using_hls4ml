import tensorflow as tf
from tensorflow.keras import layers, models

# ==============================
# Load MNIST Dataset
# ==============================

(x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

# Normalize
x_train = x_train.astype("float32") / 255.0
x_test = x_test.astype("float32") / 255.0

# Add channel dimension
x_train = x_train[..., tf.newaxis]
x_test = x_test[..., tf.newaxis]

# ==============================
# Build LeNet
# ==============================

model = models.Sequential([

    layers.Conv2D(
        filters=6,
        kernel_size=(5,5),
        activation='relu',
        input_shape=(28,28,1)
    ),

    layers.AveragePooling2D(),

    layers.Conv2D(
        filters=16,
        kernel_size=(5,5),
        activation='relu'
    ),

    layers.AveragePooling2D(),

    layers.Flatten(),

    layers.Dense(
        120,
        activation='relu'
    ),

    layers.Dense(
        84,
        activation='relu'
    ),

    layers.Dense(
        10,
        activation='softmax'
    )

])

# ==============================
# Compile
# ==============================

model.compile(
    optimizer='adam',
    loss='sparse_categorical_crossentropy',
    metrics=['accuracy']
)

# ==============================
# Train
# ==============================

model.fit(
    x_train,
    y_train,
    epochs=5,
    batch_size=128,
    validation_split=0.1
)

# ==============================
# Test
# ==============================

loss, acc = model.evaluate(
    x_test,
    y_test
)

print("Accuracy =", acc)

# ==============================
# Save
# ==============================

model.save("lenet_mnist_fp32.h5")

print("Model saved successfully.")
