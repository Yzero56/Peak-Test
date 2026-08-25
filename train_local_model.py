import os
import numpy as np
from PIL import Image
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.keras import layers, models

# Load images
dataset_dir = "xiao_dataset"
image_size = (96, 96)  # Smaller for faster training

images = []
labels = []
label_map = {}

files = sorted([f for f in os.listdir(dataset_dir) if f.endswith(".jpg")])

for i, filename in enumerate(files):
    # Extract label
    label = filename.replace(".jpg", "").split(".")[0]
    
    if label not in label_map:
        label_map[label] = len(label_map)
    
    # Load and resize image
    img_path = os.path.join(dataset_dir, filename)
    img = Image.open(img_path).resize(image_size)
    img_array = np.array(img) / 255.0  # Normalize
    
    images.append(img_array)
    labels.append(label_map[label])

# Convert to numpy arrays
X = np.array(images)
y = np.array(labels)
num_classes = len(label_map)

print(f"Dataset: {len(X)} images, {num_classes} classes")
print(f"Classes: {label_map}")

# Split dataset
X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

# Build simple CNN model
model = models.Sequential([
    layers.Conv2D(32, (3, 3), activation='relu', input_shape=(96, 96, 3)),
    layers.MaxPooling2D((2, 2)),
    layers.Conv2D(64, (3, 3), activation='relu'),
    layers.MaxPooling2D((2, 2)),
    layers.Conv2D(64, (3, 3), activation='relu'),
    layers.Flatten(),
    layers.Dense(64, activation='relu'),
    layers.Dense(num_classes, activation='softmax')
])

# Compile model
model.compile(optimizer='adam',
              loss='sparse_categorical_crossentropy',
              metrics=['accuracy'])

# Train model
print("\nTraining model...")
history = model.fit(X_train, y_train, 
                    epochs=10, 
                    validation_data=(X_val, y_val))

# Save model in TensorFlow Lite format
print("\nSaving TensorFlow Lite model...")
converter = tf.lite.TFLiteConverter.from_keras_model(model)
tflite_model = converter.convert()

with open('model.tflite', 'wb') as f:
    f.write(tflite_model)

print("Model saved as model.tflite")

# Save label map
with open('labels.txt', 'w') as f:
    for label in label_map:
        f.write(f"{label}\n")

print("Labels saved as labels.txt")

print("\n=== Training Complete ===")
print(f"Model accuracy: {history.history['val_accuracy'][-1]:.2f}")
print(f"Model saved: model.tflite")
print(f"Labels: labels.txt")
