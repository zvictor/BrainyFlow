from brainyflow import Node, Flow
from utils import call_llm

class UserInputNode(Node):
    async def prep(self, shared):
        # Initialize messages if this is the first run
        if "messages" not in shared:
            shared["messages"] = []
            print("Welcome to the Travel Advisor Chat! Type 'exit' to end the conversation.")
        
        return None

    async def exec(self, _):
        # Get user input
        user_input = input("\nYou: ")
        return user_input

    async def post(self, shared, prep_res, exec_res):
        user_input = exec_res
        
        # Check if user wants to exit
        if user_input and user_input.lower() == 'exit':
            print("\nGoodbye! Safe travels!")
            return None  # End the conversation
        
        # Store user input in shared
        shared["user_input"] = user_input
        
        # Move to guardrail validation
        self.trigger("validate")

class GuardrailNode(Node):
    async def prep(self, shared):
        # Get the user input from shared data
        user_input = getattr(shared, "user_input", "")
        return user_input
    
    async def exec(self, user_input):
        # Basic validation checks
        if not user_input or user_input.strip() == "":
            return False, "Your query is empty. Please provide a travel-related question."
        
        if len(user_input.strip()) < 3:
            return False, "Your query is too short. Please provide more details about your travel question."
        
        # LLM-based validation for travel topics
        prompt = f"""
Evaluate if the following user query is related to travel advice, destinations, planning, or other travel topics.
The chat should ONLY answer travel-related questions and reject any off-topic, harmful, or inappropriate queries.
User query: {user_input}
Return your evaluation in YAML format:
```yaml
valid: true/false
reason: [Explain why the query is valid or invalid]
```

IMPORTANT: Make sure to:
1. Use proper indentation (4 spaces) for all multi-line fields
2. Use the | character for multi-line text fields
3. Keep single-line fields without the | character
4. Your answer must be wrapped in yaml code block or it will result in an error. Do not forget to include the ```yaml sequence at the beginning and end it with ```.
"""
        
        # Call LLM with the validation prompt
        messages = [{"role": "user", "content": prompt}]
        response = call_llm(messages)
        assert "```yaml" in response, "Response must contain yaml block"
        
        # Extract YAML content
        yaml_content = response.split("```yaml")[1].split("```")[0].strip() if "```yaml" in response else response
        
        import yaml
        result = yaml.safe_load(yaml_content)
        assert result is not None, "Error: Invalid YAML format"
        assert "valid" in result and "reason" in result, "Error: Invalid YAML format"
        is_valid = result.get("valid", False)
        reason = result.get("reason", "Missing reason in YAML response")
        
        return is_valid, reason
    
    async def post(self, shared, prep_res, exec_res):
        is_valid, message = exec_res
        
        if not is_valid:
            # Display error message to user
            print(f"\nTravel Advisor: {message}")
            # Skip LLM call and go back to user input
            return "retry"
        
        # Valid input, add to message history
        shared["messages"].append({"role": "user", "content": shared["user_input"]})
        # Proceed to LLM processing
        self.trigger("process")

class LLMNode(Node):
    async def prep(self, shared):
        # Add system message if not present
        if not any(msg.get("role") == "system" for msg in shared["messages"]):
            shared["messages"].insert(0, {
                "role": "system", 
                "content": "You are a helpful travel advisor that provides information about destinations, travel planning, accommodations, transportation, activities, and other travel-related topics. Only respond to travel-related queries and keep responses informative and friendly. Your response are concise in 100 words."
            })
        
        # Return all messages for the LLM
        return shared["messages"]

    async def exec(self, messages):
        # Call LLM with the entire conversation history
        response = call_llm(messages)
        return response

    async def post(self, shared, prep_res, exec_res):
        # Print the assistant's response
        print(f"\nTravel Advisor: {exec_res}")
        
        # Add assistant message to history
        shared["messages"].append({"role": "assistant", "content": exec_res})
        
        # Loop back to continue the conversation
        self.trigger("continue")

# Create the flow with nodes and connections
user_input_node = UserInputNode()
guardrail_node = GuardrailNode()
llm_node = LLMNode()

# Create flow connections
user_input_node - "validate" >> guardrail_node
guardrail_node - "retry" >> user_input_node  # Loop back if input is invalid
guardrail_node - "process" >> llm_node
llm_node - "continue" >> user_input_node     # Continue conversation

flow = Flow(start=user_input_node)

async def main():
    shared = {}
    await flow.run(shared)

# Start the chat
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
