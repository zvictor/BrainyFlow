---
machine-display: false
---

# Installation

BrainyFlow is currently available for both Python and TypeScript.

{% tabs %}
{% tab title="Python" %}
You can install the Python package using pip:

```bash
pip install brainyflow
```

{% endtab %}

{% tab title="TypeScript" %}
You can install the TypeScript package using pnpm (or npm/yarn):

```bash
pnpm add brainyflow
# or
npm install brainyflow
# or
yarn add brainyflow
```

{% endtab %}

{% tab title="JavaScript (Browser)" %}
You can import the JavaScript file directly in the browser using a `<script>` tag:

```html
<script type="module">
  import * as brainyflow from 'https://unpkg.com/brainyflow@latest/dist/brainyflow.js'

  new brainyflow.Node(...)
</script>
```

or

```html
<script type="module" src="https://unpkg.com/brainyflow@latest/dist/brainyflow.js"></script>
<script>
  new globalThis.brainyflow.Node(...)
</script>
```

{% endtab %}
{% endtabs %}

## Alternative: Copy the Source Code

Since BrainyFlow is lightweight and dependency-free, you can also install it by simply copying the source code file directly into your project:

{% tabs %}
{% tab title="Python" %}
Copy [`python/brainyflow.py`](https://github.com/zvictor/BrainyFlow/blob/main/python/brainyflow.py)
{% endtab %}

{% tab title="TypeScript" %}
Copy [`typescript/brainyflow.ts`](https://github.com/zvictor/BrainyFlow/blob/main/typescript/brainyflow.ts)
{% endtab %}
{% endtabs %}

## Next Steps

Once you have BrainyFlow installed, check out the [Getting Started](./getting_started.md) guide to build your first flow, or explore the [Core Abstractions](./core_abstraction/node.md) to understand the framework's fundamental concepts.
