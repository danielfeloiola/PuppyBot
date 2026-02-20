"""
=============================================================================
Bluesky Account API Skeleton
=============================================================================

Esqueleto para manipular uma conta Bluesky via API REST.
Cobre as operações mais comuns: postar, curtir, seguir, buscar, etc.

Instalação:
    pip install atproto

Autenticação:
    1. Abra o Bluesky → Settings → App Passwords
    2. Crie uma App Password
    3. Use seu handle + app password (NUNCA sua senha real)

Uso:
    python bluesky_account_skeleton.py

=============================================================================
"""

import logging
from pathlib import Path
from dataclasses import dataclass

from atproto import Client, client_utils, models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bsky")


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

@dataclass
class AccountConfig:
    handle: str = "seu-handle.bsky.social"
    app_password: str = "sua-app-password"


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class BlueskyAccount:
    """
    Wrapper sobre o SDK atproto com métodos organizados por categoria.
    Cada método é independente — use como referência e copie o que precisar.
    """

    def __init__(self, config: AccountConfig):
        self.client = Client()
        self.config = config
        self.profile = None

    def login(self):
        """Autentica na API. Necessário antes de qualquer operação."""
        self.profile = self.client.login(
            self.config.handle,
            self.config.app_password,
        )
        log.info(f"Logado como: {self.profile.display_name} (@{self.profile.handle})")
        log.info(f"DID: {self.profile.did}")
        return self.profile

    # ===================================================================
    # PERFIL
    # ===================================================================

    def get_my_profile(self) -> dict:
        """Retorna o perfil completo da conta logada."""
        profile = self.client.get_profile(self.config.handle)
        log.info(f"Handle:     @{profile.handle}")
        log.info(f"Nome:       {profile.display_name}")
        log.info(f"Bio:        {profile.description}")
        log.info(f"Seguidores: {profile.followers_count}")
        log.info(f"Seguindo:   {profile.follows_count}")
        log.info(f"Posts:       {profile.posts_count}")
        return profile

    def get_profile(self, handle: str) -> dict:
        """Retorna o perfil de qualquer usuário."""
        return self.client.get_profile(handle)

    def update_profile(
        self,
        display_name: str | None = None,
        description: str | None = None,
        avatar_path: str | None = None,
    ):
        """
        Atualiza nome, bio e/ou avatar do perfil.
        Passa None nos campos que não quer alterar.
        """
        # Busca perfil atual pra preservar campos não alterados
        current = self.client.get_profile(self.config.handle)

        # Upload do avatar se fornecido
        avatar_blob = None
        if avatar_path:
            with open(avatar_path, "rb") as f:
                avatar_blob = self.client.upload_blob(f.read()).blob

        # Monta o record de perfil atualizado
        # Nota: o SDK usa com.atproto.repo.putRecord por baixo
        self.client.com.atproto.repo.put_record(
            models.ComAtprotoRepoPutRecord.Data(
                repo=self.profile.did,
                collection="app.bsky.actor.profile",
                rkey="self",
                record=models.AppBskyActorProfile.Record(
                    display_name=display_name or current.display_name,
                    description=description or current.description,
                    avatar=avatar_blob or current.avatar,
                ),
            )
        )
        log.info("Perfil atualizado!")

    # ===================================================================
    # IDENTIDADE
    # ===================================================================

    def resolve_handle(self, handle: str) -> str:
        """Converte handle → DID."""
        resp = self.client.com.atproto.identity.resolve_handle(
            {"handle": handle}
        )
        log.info(f"@{handle} → {resp.did}")
        return resp.did

    def resolve_did(self, did: str) -> dict:
        """
        Busca o perfil de um DID.
        Útil pra converter DIDs do Jetstream em informações legíveis.
        """
        profile = self.client.get_profile(did)
        log.info(f"{did} → @{profile.handle} ({profile.display_name})")
        return profile

    # ===================================================================
    # POSTS — Criar
    # ===================================================================

    def post_text(self, text: str) -> dict:
        """Post simples de texto."""
        resp = self.client.send_post(text=text)
        log.info(f"Post criado: {resp.uri}")
        return resp

    def post_with_link(self, text_before: str, link_text: str, url: str, text_after: str = "") -> dict:
        """Post com link clicável (rich text)."""
        builder = (
            client_utils.TextBuilder()
            .text(text_before)
            .link(link_text, url)
            .text(text_after)
        )
        resp = self.client.send_post(builder)
        log.info(f"Post com link criado: {resp.uri}")
        return resp

    def post_with_mention(self, text_before: str, handle: str, text_after: str = "") -> dict:
        """Post mencionando outro usuário."""
        # Resolve o DID do mencionado
        did = self.resolve_handle(handle)
        builder = (
            client_utils.TextBuilder()
            .text(text_before)
            .mention(handle, did)
            .text(text_after)
        )
        resp = self.client.send_post(builder)
        log.info(f"Post com menção criado: {resp.uri}")
        return resp

    def post_with_image(self, text: str, image_path: str, alt_text: str = "") -> dict:
        """Post com imagem anexada."""
        with open(image_path, "rb") as f:
            image_data = f.read()

        resp = self.client.send_image(
            text=text,
            image=image_data,
            image_alt=alt_text,
        )
        log.info(f"Post com imagem criado: {resp.uri}")
        return resp

    def post_reply(self, text: str, parent_uri: str, parent_cid: str, root_uri: str, root_cid: str) -> dict:
        """
        Responde a um post existente.

        Para responder ao post diretamente (não a uma thread):
            root_uri = parent_uri
            root_cid = parent_cid
        """
        parent_ref = models.create_strong_ref(parent_uri, parent_cid)
        root_ref = models.create_strong_ref(root_uri, root_cid)

        resp = self.client.send_post(
            text=text,
            reply_to=models.AppBskyFeedPost.ReplyRef(
                parent=parent_ref,
                root=root_ref,
            ),
        )
        log.info(f"Reply criado: {resp.uri}")
        return resp

    def post_quote(self, text: str, quoted_uri: str, quoted_cid: str) -> dict:
        """Quote post (repost com comentário)."""
        embed = models.AppBskyEmbedRecord.Main(
            record=models.create_strong_ref(quoted_uri, quoted_cid),
        )
        resp = self.client.send_post(text=text, embed=embed)
        log.info(f"Quote post criado: {resp.uri}")
        return resp

    # ===================================================================
    # POSTS — Interagir
    # ===================================================================

    def like(self, uri: str, cid: str) -> dict:
        """Curte um post."""
        resp = self.client.like(uri, cid)
        log.info(f"Like: {uri}")
        return resp

    def unlike(self, like_uri: str):
        """Remove curtida. Precisa da URI do like (não do post)."""
        self.client.delete_like(like_uri)
        log.info(f"Unlike: {like_uri}")

    def repost(self, uri: str, cid: str) -> dict:
        """Reposta um post."""
        resp = self.client.repost(uri, cid)
        log.info(f"Repost: {uri}")
        return resp

    def unrepost(self, repost_uri: str):
        """Remove repost. Precisa da URI do repost."""
        self.client.delete_repost(repost_uri)
        log.info(f"Unrepost: {repost_uri}")

    def delete_post(self, post_uri: str):
        """Deleta um post seu."""
        self.client.delete_post(post_uri)
        log.info(f"Post deletado: {post_uri}")

    # ===================================================================
    # TIMELINE & FEEDS
    # ===================================================================

    def get_timeline(self, limit: int = 20) -> list:
        """Retorna posts da timeline (feed principal)."""
        resp = self.client.get_timeline(limit=limit)
        posts = []
        for item in resp.feed:
            post = item.post
            posts.append({
                "uri": post.uri,
                "cid": post.cid,
                "author": post.author.handle,
                "text": post.record.text,
                "likes": post.like_count,
                "reposts": post.repost_count,
                "replies": post.reply_count,
                "created_at": post.record.created_at,
            })
            log.info(f"  @{post.author.handle}: {post.record.text[:80]}")
        return posts

    def get_author_feed(self, handle: str, limit: int = 20) -> list:
        """Retorna posts de um autor específico."""
        resp = self.client.get_author_feed(handle, limit=limit)
        posts = []
        for item in resp.feed:
            post = item.post
            posts.append({
                "uri": post.uri,
                "cid": post.cid,
                "text": post.record.text,
                "likes": post.like_count,
                "created_at": post.record.created_at,
            })
        log.info(f"{len(posts)} posts de @{handle}")
        return posts

    def get_post_thread(self, uri: str, depth: int = 10) -> dict:
        """Retorna uma thread completa a partir de um post."""
        resp = self.client.get_post_thread(uri, depth=depth)
        log.info(f"Thread carregada: {uri}")
        return resp

    # ===================================================================
    # BUSCA
    # ===================================================================

    def search_posts(self, query: str, limit: int = 25, lang: str | None = None) -> list:
        """
        Busca posts por termo.
        Equivalente ao search/tweets do Twitter.
        """
        params = {"q": query, "limit": limit}
        if lang:
            params["lang"] = lang

        resp = self.client.app.bsky.feed.search_posts(params)
        results = []
        for post in resp.posts:
            results.append({
                "uri": post.uri,
                "cid": post.cid,
                "author": post.author.handle,
                "text": post.record.text,
                "likes": post.like_count,
                "created_at": post.record.created_at,
                "langs": getattr(post.record, "langs", []),
            })
        log.info(f"Busca '{query}': {len(results)} resultados")
        return results

    def search_users(self, query: str, limit: int = 10) -> list:
        """Busca perfis de usuários."""
        resp = self.client.app.bsky.actor.search_actors({"q": query, "limit": limit})
        users = []
        for actor in resp.actors:
            users.append({
                "did": actor.did,
                "handle": actor.handle,
                "display_name": actor.display_name,
                "description": actor.description,
                "followers": actor.followers_count,
            })
            log.info(f"  @{actor.handle} ({actor.display_name}) — {actor.followers_count} seguidores")
        return users

    # ===================================================================
    # GRAFO SOCIAL — Follows, Blocks, Mutes
    # ===================================================================

    def follow(self, did: str) -> dict:
        """Segue um usuário (por DID)."""
        resp = self.client.follow(did)
        log.info(f"Seguindo: {did}")
        return resp

    def unfollow(self, follow_uri: str):
        """Deixa de seguir. Precisa da URI do follow."""
        self.client.delete_follow(follow_uri)
        log.info(f"Unfollow: {follow_uri}")

    def block(self, did: str) -> dict:
        """Bloqueia um usuário."""
        resp = self.client.app.bsky.graph.block.create(
            self.profile.did,
            models.AppBskyGraphBlock.Record(
                subject=did,
                created_at=self.client.get_current_time_iso(),
            ),
        )
        log.info(f"Bloqueado: {did}")
        return resp

    def mute(self, did: str):
        """Muta um usuário (silencia sem bloquear)."""
        self.client.mute(did)
        log.info(f"Mutado: {did}")

    def unmute(self, did: str):
        """Remove mute."""
        self.client.unmute(did)
        log.info(f"Unmute: {did}")

    def get_followers(self, handle: str, limit: int = 50) -> list:
        """Lista seguidores de um usuário."""
        resp = self.client.get_followers(handle, limit=limit)
        followers = []
        for f in resp.followers:
            followers.append({
                "did": f.did,
                "handle": f.handle,
                "display_name": f.display_name,
            })
        log.info(f"@{handle}: {len(followers)} seguidores carregados")
        return followers

    def get_follows(self, handle: str, limit: int = 50) -> list:
        """Lista quem um usuário segue."""
        resp = self.client.get_follows(handle, limit=limit)
        follows = []
        for f in resp.follows:
            follows.append({
                "did": f.did,
                "handle": f.handle,
                "display_name": f.display_name,
            })
        log.info(f"@{handle}: seguindo {len(follows)} contas")
        return follows

    def get_all_followers(self, handle: str) -> list:
        """
        Pagina por TODOS os seguidores (sem limite).
        Cuidado: pode ser lento para contas com muitos seguidores.
        """
        all_followers = []
        cursor = None

        while True:
            params = {"actor": handle, "limit": 100}
            if cursor:
                params["cursor"] = cursor

            resp = self.client.app.bsky.graph.get_followers(params)
            all_followers.extend([
                {"did": f.did, "handle": f.handle, "display_name": f.display_name}
                for f in resp.followers
            ])

            cursor = resp.cursor
            if not cursor:
                break

            log.info(f"  Paginando... {len(all_followers)} seguidores até agora")

        log.info(f"@{handle}: {len(all_followers)} seguidores (total)")
        return all_followers

    # ===================================================================
    # LISTAS
    # ===================================================================

    def get_lists(self, handle: str) -> list:
        """Lista todas as listas de um usuário."""
        resp = self.client.app.bsky.graph.get_lists({"actor": handle})
        lists = []
        for lst in resp.lists:
            lists.append({
                "uri": lst.uri,
                "name": lst.name,
                "purpose": lst.purpose,
                "description": lst.description,
                "list_item_count": lst.list_item_count,
            })
            log.info(f"  Lista: {lst.name} ({lst.list_item_count} itens)")
        return lists

    # ===================================================================
    # NOTIFICAÇÕES
    # ===================================================================

    def get_notifications(self, limit: int = 20) -> list:
        """Retorna notificações recentes."""
        resp = self.client.app.bsky.notification.list_notifications({"limit": limit})
        notifs = []
        for n in resp.notifications:
            notifs.append({
                "reason": n.reason,  # like, repost, follow, mention, reply, quote
                "author": n.author.handle,
                "is_read": n.is_read,
                "indexed_at": n.indexed_at,
            })
            log.info(f"  [{n.reason}] @{n.author.handle}")
        return notifs


# ---------------------------------------------------------------------------
# Exemplo de uso
# ---------------------------------------------------------------------------

def main():
    config = AccountConfig(
        handle="seu-handle.bsky.social",
        app_password="sua-app-password",
    )

    bsky = BlueskyAccount(config)
    bsky.login()

    # --- Exemplos (descomente o que quiser testar) ---

    # Perfil
    # bsky.get_my_profile()
    # bsky.resolve_handle("bsky.app")

    # Postar
    # bsky.post_text("Teste via API!")
    # bsky.post_with_link("Confira: ", "AT Protocol SDK", "https://atproto.blue")

    # Timeline
    # bsky.get_timeline(limit=5)

    # Busca
    # bsky.search_posts("desinformação", limit=10, lang="pt")
    # bsky.search_users("jornalismo")

    # Grafo social
    # bsky.get_followers("bsky.app", limit=10)
    # bsky.get_follows("bsky.app", limit=10)

    # Notificações
    # bsky.get_notifications(limit=10)


if __name__ == "__main__":
    main()
