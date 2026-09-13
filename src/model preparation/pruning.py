import tensorflow as tf

model = tf.keras.models.load_model("lenet_mnist_fp32.h5")

model.summary()

import tensorflow_model_optimization as tfmot

pruning_params = {
    "pruning_schedule":
    tfmot.sparsity.keras.ConstantSparsity(
        target_sparsity=0.50,
        begin_step=0
    )
}

pruned_model = tfmot.sparsity.keras.prune_low_magnitude(
    model,
    **pruning_params
)

pruned_model.compile(
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

(x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

x_train = x_train.astype("float32") / 255.0
x_test = x_test.astype("float32") / 255.0

x_train = x_train[..., tf.newaxis]
x_test = x_test[..., tf.newaxis]

callbacks = [
    tfmot.sparsity.keras.UpdatePruningStep()
]

pruned_model.fit(
    x_train,
    y_train,
    epochs=3,
    validation_split=0.1,
    callbacks=callbacks
)

loss, acc = pruned_model.evaluate(x_test, y_test)

print("Accuracy =", acc)

final_model = tfmot.sparsity.keras.strip_pruning(pruned_model)

final_model.save("lenet_mnist_pruned50.h5")
