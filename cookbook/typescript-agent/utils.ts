import OpenAI from 'openai'
import { DDGS } from '@phukon/duckduckgo-search'

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

export async function callLLM(messages: Message[]) {
 const client = new OpenAI({
   apiKey: process.env.OPENAI_API_KEY
 })

 const response = await client.chat.completions.create({
   model: 'gpt-4o-mini',
   messages: messages,
   temperature: 0.7
 })

 return response.choices[0].message.content
}

export async function webSearch(query: string) {
  const ddgs = new DDGS()
  const result = await ddgs.text({
    keywords: query,
    maxResults: 5,
  })

  return result
}
