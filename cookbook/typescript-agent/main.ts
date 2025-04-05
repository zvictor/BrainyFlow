import { createAgentFlow } from "./flow";
import { SearchAgentSharedContext } from "./nodes";

async function main() {
    const question = "what is agentic ai?";
    const agentFlow = createAgentFlow();
    const sharedContext: SearchAgentSharedContext = {
        question: question,
    }
    await agentFlow.run(sharedContext);
}

main().catch((error) => {
    console.error("Error running the agent:", error);
}
);
