---
complexity: 7
---

# Batch Flow Example

This example demonstrates the batch Flow concept in BrainyFlow by implementing an image processor that applies different filters to multiple images.

## What this Example Demonstrates

- How to use batch Flow to run a Flow multiple times with different parameters
- Key concepts of batch Flow:
  1. Creating a base Flow for single-item processing
  2. Using batch Flow to process multiple items with different parameters
  3. Managing parameters across multiple Flow executions

## Project Structure

```
brainyflow-batch-flow/
├── README.md
├── requirements.txt
├── images/
│   ├── cat.jpg        # Sample image 1
│   ├── dog.jpg        # Sample image 2
│   └── bird.jpg       # Sample image 3
├── main.py            # Entry point
├── flow.py            # Flow and batch Flow definitions
└── nodes.py           # Node implementations for image processing
```

## How it Works

The example processes multiple images with different filters:

1. **Base Flow**: Processes a single image

   - Load image
   - Apply filter (grayscale, blur, or sepia)
   - Save processed image

2. **batch Flow**: Processes multiple image-filter combinations
   - Takes a list of parameters (image + filter combinations)
   - Runs the base Flow for each parameter set
   - Organizes output in a structured way

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

## Sample Output

```
Processing images with filters...

Processing cat.jpg with grayscale filter...
Processing cat.jpg with blur filter...
Processing dog.jpg with sepia filter...
...

All images processed successfully!
Check the 'output' directory for results.
```

## Key Concepts Illustrated

1. **Parameter Management**: Shows how batch Flow manages different parameter sets
2. **Flow Reuse**: Demonstrates running the same Flow multiple times
3. **Batch Processing**: Shows how to process multiple items efficiently
4. **Real-world Application**: Provides a practical example of batch processing
