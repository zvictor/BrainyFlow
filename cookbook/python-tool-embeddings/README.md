---
complexity: 3
---

# OpenAI Embeddings with BrainyFlow

This example demonstrates how to properly integrate OpenAI's text embeddings API with BrainyFlow, focusing on:

1. Clean code organization with separation of concerns:

   - Tools layer for API interactions (`tools/embeddings.py`)
   - Node implementation for BrainyFlow integration (`nodes.py`)
   - Flow configuration (`flow.py`)
   - Centralized environment configuration (`utils/call_llm.py`)

2. Best practices for API key management:

   - Using environment variables
   - Supporting both `.env` files and system environment variables
   - Secure configuration handling

3. Proper project structure:
   - Modular code organization
   - Clear separation between tools and BrainyFlow components
   - Reusable OpenAI client configuration

## Project Structure

```
brainyflow-tool-embeddings/
├── tools/
│   └── embeddings.py     # OpenAI embeddings API wrapper
├── utils/
│   └── call_llm.py      # Centralized OpenAI client configuration
├── nodes.py             # BrainyFlow node implementation
├── flow.py             # Flow configuration
└── main.py             # Example usage
```

## Setup

1. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up your OpenAI API key in one of two ways:

   a. Using a `.env` file:

   ```bash
   OPENAI_API_KEY=your_api_key_here
   ```

   b. Or as a system environment variable:

   ```bash
   export OPENAI_API_KEY=your_api_key_here
   ```

## Usage

Run the example:

```bash
python main.py
```

This will:

1. Load the OpenAI API key from environment
2. Create a BrainyFlow node to handle embedding generation
3. Process a sample text and generate its embedding
4. Display the embedding dimension and first few values

## Key Concepts Demonstrated

1. **Environment Configuration**

   - Secure API key handling
   - Flexible configuration options

2. **Code Organization**

   - Clear separation between tools and BrainyFlow components
   - Reusable OpenAI client configuration
   - Modular project structure

3. **BrainyFlow Integration**
   - Node implementation with prep->exec->post lifecycle
   - Flow configuration
   - Shared store usage for data passing
