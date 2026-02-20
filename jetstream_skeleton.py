"""
Jetstream Skeleton — Esqueleto base para consumir o Bluesky Jetstream.

Uso:
    pip install websockets
    python jetstream_skeleton.py

O que esse esqueleto faz:
    1. Conecta ao Jetstream (WebSocket público, sem autenticação)
    2. Filtra por collections e/ou DIDs configuráveis
    3. Reconecta automaticamente se a conexão cair (com cursor)
    4. Dispatcha eventos para handlers por tipo
    5. Loga estatísticas periódicas

Adapte os handlers para o que você precisar:
    - Salvar num banco de dados
    - Filtrar por keywords
    - Alimentar um pipeline de análise
    - Etc.
"""

import json
import asyncio
import signal
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import websockets

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jetstream")


@dataclass
class JetstreamConfig:
    """Configuração do cliente Jetstream."""

    # Instâncias públicas oficiais do Bluesky:
    #   jetstream1.us-east.bsky.network
    #   jetstream2.us-east.bsky.network
    #   jetstream1.us-west.bsky.network
    #   jetstream2.us-west.bsky.network
    host: str = "jetstream2.us-east.bsky.network"

    # Collections para filtrar (vazio = tudo).
    # Exemplos:
    #   "app.bsky.feed.post"     — posts
    #   "app.bsky.feed.like"     — curtidas
    #   "app.bsky.feed.repost"   — reposts
    #   "app.bsky.graph.follow"  — follows
    #   "app.bsky.graph.block"   — bloqueios
    #   "app.bsky.feed.*"        — wildcard
    wanted_collections: list[str] = field(default_factory=lambda: [
        "app.bsky.feed.post",
    ])

    # DIDs específicos para monitorar (vazio = todos).
    # Máximo: 10.000 por conexão.
    wanted_dids: list[str] = field(default_factory=list)

    # Compressão zstd (~56% menor). Precisa da lib `zstandard` instalada.
    compress: bool = False

    # Intervalo (em eventos) para log de estatísticas.
    stats_interval: int = 500

    # Delay base para reconexão (segundos). Dobra a cada falha consecutiva.
    reconnect_delay: float = 1.0
    reconnect_max_delay: float = 30.0

    def build_url(self, cursor: int | None = None) -> str:
        """Monta a URL de conexão com os parâmetros de filtro."""
        params = []

        for col in self.wanted_collections:
            params.append(f"wantedCollections={col}")

        for did in self.wanted_dids:
            params.append(f"wantedDids={did}")

        if self.compress:
            params.append("compress=true")

        if cursor is not None:
            params.append(f"cursor={cursor}")

        query = "&".join(params)
        return f"wss://{self.host}/subscribe?{query}" if query else f"wss://{self.host}/subscribe"


# ---------------------------------------------------------------------------
# Handlers 
# ---------------------------------------------------------------------------

class EventHandler:
    """
    Handlers para cada tipo de evento.
    """

    async def on_post_create(self, did: str, rkey: str, record: dict, raw: dict):
        """Chamado quando um post é criado."""
        text = record.get("text", "")
        langs = record.get("langs", [])
        log.info(f"POST [{','.join(langs)}] {did[:25]}… → {text[:100]}")

    async def on_post_delete(self, did: str, rkey: str, raw: dict):
        """Chamado quando um post é deletado."""
        log.debug(f"DELETE post {did}:{rkey}")

    async def on_like(self, did: str, rkey: str, record: dict, raw: dict):
        """Chamado quando alguém curte algo."""
        subject_uri = record.get("subject", {}).get("uri", "")
        log.debug(f"LIKE {did[:25]}… → {subject_uri}")

    async def on_repost(self, did: str, rkey: str, record: dict, raw: dict):
        """Chamado quando alguém reposta algo."""
        subject_uri = record.get("subject", {}).get("uri", "")
        log.debug(f"REPOST {did[:25]}… → {subject_uri}")

    async def on_follow(self, did: str, rkey: str, record: dict, raw: dict):
        """Chamado quando alguém segue outro usuário."""
        subject = record.get("subject", "")
        log.debug(f"FOLLOW {did[:25]}… → {subject}")

    async def on_identity(self, did: str, raw: dict):
        """Chamado em mudança de handle ou DID doc."""
        log.debug(f"IDENTITY {did}")

    async def on_account(self, did: str, raw: dict):
        """Chamado em mudança de status de conta (ativação, suspensão, etc)."""
        log.debug(f"ACCOUNT {did}")


# ---------------------------------------------------------------------------
# Cliente Jetstream
# ---------------------------------------------------------------------------

class JetstreamClient:
    """
    Cliente que conecta ao Jetstream, processa eventos,
    e reconecta automaticamente.
    """

    def __init__(self, config: JetstreamConfig, handler: EventHandler):
        self.config = config
        self.handler = handler
        self.cursor: int | None = None
        self.running = False

        # Estatísticas
        self.stats = {
            "events": 0,
            "posts": 0,
            "likes": 0,
            "reposts": 0,
            "follows": 0,
            "deletes": 0,
            "errors": 0,
        }
        self._started_at: datetime | None = None

    async def start(self):
        """Inicia o cliente com reconexão automática."""
        self.running = True
        self._started_at = datetime.now(timezone.utc)
        delay = self.config.reconnect_delay

        log.info(f"Jetstream client iniciando...")
        log.info(f"  Host: {self.config.host}")
        log.info(f"  Collections: {self.config.wanted_collections}")
        log.info(f"  DIDs: {len(self.config.wanted_dids)} configurados")
        log.info(f"  Compressão: {'sim' if self.config.compress else 'não'}")

        while self.running:
            try:
                await self._connect()
                delay = self.config.reconnect_delay  # Reset delay após sucesso
            except (
                websockets.ConnectionClosed,
                websockets.InvalidStatusCode,
                ConnectionError,
                OSError,
            ) as e:
                log.warning(f"Conexão perdida: {e}")
            except Exception as e:
                log.error(f"Erro inesperado: {e}", exc_info=True)
                self.stats["errors"] += 1

            if self.running:
                log.info(f"Reconectando em {delay:.1f}s (cursor={self.cursor})...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.config.reconnect_max_delay)

    async def stop(self):
        """Para o cliente."""
        log.info("Parando Jetstream client...")
        self.running = False

    async def update_filters(
        self,
        ws,
        collections: list[str] | None = None,
        dids: list[str] | None = None,
    ):
        """
        Atualiza filtros em runtime sem reconectar.
        Útil para adicionar/remover DIDs ou collections dinamicamente.
        """
        payload = {}
        if collections is not None:
            payload["wantedCollections"] = collections
        if dids is not None:
            payload["wantedDids"] = dids

        message = json.dumps({"type": "options_update", "payload": payload})
        await ws.send(message)
        log.info(f"Filtros atualizados: {payload}")

    def print_stats(self):
        """Imprime estatísticas acumuladas."""
        elapsed = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        rate = self.stats["events"] / elapsed if elapsed > 0 else 0

        log.info(
            f"STATS | "
            f"eventos: {self.stats['events']} | "
            f"posts: {self.stats['posts']} | "
            f"likes: {self.stats['likes']} | "
            f"reposts: {self.stats['reposts']} | "
            f"follows: {self.stats['follows']} | "
            f"deletes: {self.stats['deletes']} | "
            f"erros: {self.stats['errors']} | "
            f"rate: {rate:.1f}/s | "
            f"uptime: {elapsed:.0f}s"
        )

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    async def _connect(self):
        """Conexão e loop principal de consumo."""
        url = self.config.build_url(cursor=self.cursor)
        log.info(f"Conectando: {url[:120]}...")

        async with websockets.connect(url) as ws:
            log.info("Conectado!")

            async for raw_message in ws:
                if not self.running:
                    break

                try:
                    event = json.loads(raw_message)
                    await self._dispatch(event)
                except json.JSONDecodeError:
                    log.warning("Mensagem não-JSON recebida, ignorando")
                    self.stats["errors"] += 1
                except Exception as e:
                    log.error(f"Erro processando evento: {e}", exc_info=True)
                    self.stats["errors"] += 1

    async def _dispatch(self, event: dict):
        """Roteia o evento para o handler correto."""
        self.stats["events"] += 1

        # Atualiza cursor
        time_us = event.get("time_us")
        if time_us:
            self.cursor = time_us

        # Log de stats periódico
        if self.stats["events"] % self.config.stats_interval == 0:
            self.print_stats()

        kind = event.get("kind")
        did = event.get("did", "")

        # Eventos de identidade e conta (sempre recebidos)
        if kind == "identity":
            await self.handler.on_identity(did, event)
            return

        if kind == "account":
            await self.handler.on_account(did, event)
            return

        # Commits (create, update, delete)
        if kind != "commit":
            return

        commit = event.get("commit", {})
        operation = commit.get("operation", "")
        collection = commit.get("collection", "")
        rkey = commit.get("rkey", "")
        record = commit.get("record", {})

        # --- Posts ---
        if collection == "app.bsky.feed.post":
            if operation == "create":
                self.stats["posts"] += 1
                await self.handler.on_post_create(did, rkey, record, event)
            elif operation == "delete":
                self.stats["deletes"] += 1
                await self.handler.on_post_delete(did, rkey, event)

        # --- Likes ---
        elif collection == "app.bsky.feed.like":
            if operation == "create":
                self.stats["likes"] += 1
                await self.handler.on_like(did, rkey, record, event)

        # --- Reposts ---
        elif collection == "app.bsky.feed.repost":
            if operation == "create":
                self.stats["reposts"] += 1
                await self.handler.on_repost(did, rkey, record, event)

        # --- Follows ---
        elif collection == "app.bsky.graph.follow":
            if operation == "create":
                self.stats["follows"] += 1
                await self.handler.on_follow(did, rkey, record, event)


# ---------------------------------------------------------------------------
# Exemplo de uso: Handler customizado
# ---------------------------------------------------------------------------

class MeuHandler(EventHandler):
    """
    Exemplo: sobrescreve só o que precisa.
    Aqui filtra posts em português com keywords específicas.
    """

    def __init__(self):
        self.keywords = [
            "desinformação", "fake news", "conspiração",
            "grande substituição", "deep state",
        ]
        self.matches: list[dict] = []

    async def on_post_create(self, did: str, rkey: str, record: dict, raw: dict):
        text = record.get("text", "")
        langs = record.get("langs", [])

        # Filtra português
        if not any(l.startswith("pt") for l in langs):
            return

        # Checa keywords
        text_lower = text.lower()
        matched = [kw for kw in self.keywords if kw in text_lower]

        if matched:
            detection = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "did": did,
                "rkey": rkey,
                "langs": langs,
                "keywords": matched,
                "text": text,
                "reply_to": record.get("reply", {}).get("parent", {}).get("uri"),
                "embed_url": record.get("embed", {}).get("external", {}).get("uri"),
            }
            self.matches.append(detection)

            log.info(f"MATCH [{', '.join(matched)}]")
            log.info(f"  {text[:200]}")
            log.info(f"  Total matches: {len(self.matches)}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main():
    config = JetstreamConfig(
        wanted_collections=["app.bsky.feed.post"],
        stats_interval=200,
    )

    handler = MeuHandler()
    client = JetstreamClient(config, handler)

    # Graceful shutdown com Ctrl+C
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(client.stop()))

    await client.start()

    # Ao parar, imprime resumo
    client.print_stats()
    log.info(f"Total de matches: {len(handler.matches)}")


if __name__ == "__main__":
    asyncio.run(main())
