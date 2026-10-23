/** Copy-paste snippets that point an OpenAI client at this gateway. */

export function gatewayBaseUrl(origin: string): string {
  return `${origin.replace(/\/+$/, "")}/v1`;
}

export function curlSnippet(origin: string, key: string, model = "chat-small"): string {
  return [
    `curl ${gatewayBaseUrl(origin)}/chat/completions \\`,
    `  -H "Authorization: Bearer ${key}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"model": "${model}", "messages": [{"role": "user", "content": "Hello"}]}'`,
  ].join("\n");
}

export function pythonSnippet(origin: string, key: string, model = "chat-small"): string {
  return [
    "from openai import OpenAI",
    "",
    "client = OpenAI(",
    `    base_url="${gatewayBaseUrl(origin)}",`,
    `    api_key="${key}",`,
    ")",
    "",
    "reply = client.chat.completions.create(",
    `    model="${model}",`,
    '    messages=[{"role": "user", "content": "Hello"}],',
    ")",
    "print(reply.choices[0].message.content)",
  ].join("\n");
}

export function nodeSnippet(origin: string, key: string, model = "chat-small"): string {
  return [
    'import OpenAI from "openai";',
    "",
    "const client = new OpenAI({",
    `  baseURL: "${gatewayBaseUrl(origin)}",`,
    `  apiKey: "${key}",`,
    "});",
    "",
    "const reply = await client.chat.completions.create({",
    `  model: "${model}",`,
    '  messages: [{ role: "user", content: "Hello" }],',
    "});",
    "console.log(reply.choices[0].message.content);",
  ].join("\n");
}
