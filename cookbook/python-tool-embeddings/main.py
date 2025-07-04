from flow import create_embedding_flow

async def main():
    # Create the flow
    flow = create_embedding_flow()
    
    # Example text
    text = "What's the meaning of life?"
    
    # Prepare shared data
    shared = {"text": text}
    
    # Run the flow
    await flow.run(shared)
    
    # Print results
    print("Text:", text)
    print("Embedding dimension:", len(shared["embedding"]))
    print("First 5 values:", shared["embedding"][:5])

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())