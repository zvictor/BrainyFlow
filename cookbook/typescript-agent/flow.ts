import { Flow } from "../../typescript/brainyflow";
import { DecideNode, SearchNode, AnswerNode } from "./nodes";

export function createAgentFlow() {
    const decideNode = new DecideNode();
    const searchNode = new SearchNode();
    const answerNode = new AnswerNode();

    decideNode.on("search", searchNode);
    decideNode.on("answer", answerNode);
    searchNode.on("decide", decideNode);

    return new Flow(decideNode);
}
