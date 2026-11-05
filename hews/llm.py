"""Thin wrapper around the AI model. Two providers:
  anthropic (default): the Claude API, needs ANTHROPIC_API_KEY
  ollama: a free local model on your own computer (no key, no cost)
If the AI is unavailable or answers badly, every agent falls back to its deterministic behaviour."""
import json, os, re, urllib.request

DEFAULT_MODEL = os.environ.get("HEWS_MODEL", "claude-sonnet-5-5")


class _Block:
    def __init__(self, text): self.text = text


class _Resp:
    def __init__(self, text): self.content = [_Block(text)]


class OllamaClient:
    """Makes a local Ollama model look like the Anthropic client."""
    def __init__(self, host: str, model: str, timeout: int = 120):
        self.host, self.model, self.timeout = host.rstrip("/"), model, timeout
        self.messages = self

    def create(self, model=None, max_tokens=700, system="", messages=None, **kw):
        payload = {"model": self.model, "stream": False, "think": False, "format": "json",
                   "options": {"num_predict": max_tokens, "temperature": 0.2},
                   "messages": [{"role": "system", "content": system}] + list(messages or [])}
        req = urllib.request.Request(self.host + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return _Resp(data["message"]["content"])

class AzureClient:
    """Makes an Azure Foundry deployment look like the Anthropic client."""
    def __init__(self, endpoint: str, api_key: str, deployment: str):
        from openai import OpenAI
        self.model = deployment
        self.client = OpenAI(base_url=endpoint.rstrip("/") + "/openai/v1/", api_key=api_key)
        self.messages = self

    def create(self, model=None, max_tokens=700, system="", messages=None, **kw):
        resp = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=max(max_tokens, 2000),
            messages=[{"role": "system", "content": system}] + list(messages or []))
        return _Resp(resp.choices[0].message.content or "")

def ollama_up(host: str) -> bool:
    try:
        urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=2).read()
        return True
    except Exception:
        return False


class LLM:
    def __init__(self, enabled: bool = True, client=None, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = client
        self.provider = "custom" if client is not None else "none"
        self.calls = 0
        if client is not None or not enabled:
            return
        provider = os.environ.get("HEWS_PROVIDER", "anthropic").lower()
        if provider == "azure":
            ep = os.environ.get("AZURE_OPENAI_ENDPOINT")
            key = os.environ.get("AZURE_OPENAI_API_KEY")
            dep = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            if ep and key and dep:
                try:
                    self.model = dep
                    self.client, self.provider = AzureClient(ep, key, dep), "azure"
                except Exception:
                    self.client = None
        elif provider == "ollama":
            host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            self.model = os.environ.get("HEWS_OLLAMA_MODEL", "qwen3:8b")
            if ollama_up(host):
                self.client, self.provider = OllamaClient(host, self.model), "ollama"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.client, self.provider = anthropic.Anthropic(), "anthropic"
            except Exception:
                self.client = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def json(self, system: str, user: str, max_tokens: int = 700):
        """Ask for a JSON object. Returns a dict, or None on any problem."""
        if not self.available:
            return None
        try:
            self.calls += 1
            resp = self.client.messages.create(
                model=self.model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
            text = "".join(getattr(b, "text", "") for b in resp.content).strip()
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception as e:
            print("LLM ERROR:", type(e).__name__, str(e)[:200])
            return None
