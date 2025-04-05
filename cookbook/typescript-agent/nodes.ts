import { parse } from 'yaml'
import { Node } from "../../typescript/brainyflow";
import { callLLM, webSearch } from "./utils";

export interface SearchAgentSharedContext {
    question: string
    context?: string
    searchQuery?: string
    answer?: string
}

interface LLMDecision {
    thinking: string
    action: 'search' | 'answer'
    reason: string
    answer?: string
    searchQuery?: string
}

interface SearchResult {
    title: string
    href: string
    body: string
}

export class DecideNode extends Node {
    async prep(shared: SearchAgentSharedContext) {
        const context = shared.context || "No previous search."
        const question = shared.question
        return { context, question };
    }

    async exec(input: { context: string, question: string }) {
        const { context, question } = input;

        console.log("Deciding whether to search or answer the question...");

        const prompt = `
        ### Context
        You are helpful assistance that can searching the web to gather real time data.
        Question: ${question}
        Context: ${context}

        ### Action Space
        [1] search
            description: look up for more information on internet
            parameter:
                - query (str): what to search for
        [2] answer
            description: answer the question based on the context
            parameter:
                - answer (str): the answer to the question
        
        ### Next Action
        Decide the next action based on the context and available actions.
        Return your response in this format:

        \`\`\`yaml
        thinking: |
            <your step-by-step reasoning process>
        action: search OR answer
        reason: <why you chose this action>
        answer: <if action is answer>
        searchQuery: <specific search query if action is search>
        \`\`\`

        IMPORTANT: Make sure to:
        1. Use proper indentation (4 spaces) for all multi-line fields
        2. Use the | character for multi-line text fields
        3. Keep single-line fields without the | character
        `
        const response = await callLLM([{role: 'user', content: prompt}]);
        const yamlStr = response!.split("```yaml")[1].split("```")[0].trim();
        const decision = parse(yamlStr) as LLMDecision;

        return decision;
    }

    async post(shared: SearchAgentSharedContext, prepRes?: { context: string, question: string }, execRes?: LLMDecision) {
        if (!prepRes) {
            console.log("No context or question provided.");
            return;
        }

        if (!execRes) {
            console.log("No decision made.");
            return;
        }
        
        if (execRes.action === 'search') {
            shared.searchQuery = execRes.searchQuery;
            console.log(`Searching for: ${execRes.searchQuery}`);
            console.log(`Reason: ${execRes.reason}`);
        } else {
            shared.answer = execRes.answer;
            console.log(`Answering: ${execRes.answer}`);
            console.log(`Reason: ${execRes.reason}`);
        }
        
        return execRes.action;
    }
}

export class SearchNode extends Node {
    async prep(shared: SearchAgentSharedContext) {
        return shared.searchQuery;
    }

    async exec(searchQuery: string) {
        console.log(`Searching for: ${searchQuery}`);
        const result = await webSearch(searchQuery);
        return result as SearchResult[];
    }

    async post(shared: SearchAgentSharedContext, prepRes?: string, execRes?: SearchResult[]) {
        if (!prepRes) {
            console.log("No search query provided.");
            return;
        }

        if (!execRes) {
            console.log("No search results found.");
            return;
        }

        const previous = shared.context || ""
        shared.context = previous + "\n\nSearch: " + shared.searchQuery + "\nResult :" + JSON.stringify(execRes);
        return 'decide';
    }
}

export class AnswerNode extends Node {
    async prep(shared: SearchAgentSharedContext) {
        const context = shared.context || "No previous context."
        const question = shared.question
        return {question, context};
    }

    async exec(input: { question: string, context: string}) {
        const { question, context } = input;
        console.log("Answering the question...");
        const prompt = `
        ### Context
        Based on the following information, answer the question.
        Question: ${question}
        Research: ${context}
        
        ## Your Answer:
        Provide a comprehensive answer using the research results.
        `
        const response = await callLLM([{role: 'user', content: prompt}]);
        return response;
    }

    async post(shared: SearchAgentSharedContext, prepRes?: string, execRes?: string) {
        if (!prepRes) {
            console.log("No answer provided.");
            return;
        }

        if (!execRes) {
            console.log("No answer generated.");
            return;
        }

        shared.answer = execRes;
        console.log(`Final Answer: ${execRes}`);
        return 'done';
    }
}
