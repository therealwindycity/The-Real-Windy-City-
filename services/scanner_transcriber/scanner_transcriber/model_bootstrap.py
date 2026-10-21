"""Deterministic local CTranslate2 model resolver/bootstrapper for faster-whisper.

Order of resolution:
1. Explicit CTranslate2 model directory containing `model.bin` and `config.json`.
2. Cached `whisper-tiny.en-ct2` directory in `cache_dir` if already prepared.
3. Standard HuggingFace Hub download via `faster_whisper.utils.download_model(model_name)`.
4. If HuggingFace Hub is unreachable (e.g., restricted GitHub-only network environments) and
   `model_name` is `tiny.en`, deterministic pure-NumPy (`allow_pickle=False`) CTranslate2 INT8
   conversion from `github.com/moonshine-ai/useful-transformers` (`examples/whisper/weights/tiny.en.npz`).
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from ctranslate2.converters import utils as ct2_utils
from ctranslate2.specs import common_spec
from ctranslate2.specs.whisper_spec import WhisperSpec
from tokenizers import AddedToken, Tokenizer, decoders, models, pre_tokenizers

logger = logging.getLogger(__name__)

WHISPER_LANGS_99 = [
    "en", "zh", "de", "es", "ru", "ko", "fr", "ja", "pt", "tr", "pl", "ca", "nl", "ar",
    "sv", "it", "id", "hi", "fi", "vi", "he", "uk", "el", "ms", "cs", "ro", "da", "hu",
    "ta", "no", "th", "ur", "hr", "bg", "lt", "la", "mi", "ml", "cy", "sk", "te", "fa",
    "lv", "bn", "sr", "az", "sl", "kn", "et", "mk", "br", "eu", "is", "hy", "ne", "mn",
    "bs", "kk", "sq", "sw", "gl", "mr", "pa", "si", "km", "sn", "yo", "so", "af", "oc",
    "ka", "be", "tg", "sd", "gu", "am", "yi", "lo", "uz", "fo", "ht", "ps", "tk", "nn",
    "mt", "sa", "lb", "my", "bo", "tl", "mg", "as", "tt", "haw", "ln", "ha", "ba", "jw", "su",
]

TINY_EN_SUPPRESS_IDS = [
    1, 2, 7, 8, 9, 10, 14, 25, 26, 27, 28, 29, 31, 58, 59, 60, 61, 62, 63, 90, 91, 92, 93,
    357, 366, 438, 532, 685, 705, 796, 930, 1058, 1220, 1267, 1279, 1303, 1343, 1377, 1391,
    1635, 1782, 1875, 2162, 2361, 2488, 3467, 4008, 4211, 4600, 4808, 5299, 5855, 6329, 7203,
    9609, 9959, 10563, 10786, 11420, 11709, 11907, 13163, 13697, 13700, 14808, 15306, 16410,
    16791, 17992, 19203, 19510, 20724, 22305, 22935, 27007, 30109, 30420, 33409, 34949, 40283,
    40493, 40549, 47282, 49146, 50257, 50357, 50358, 50359, 50360, 50361,
]


def _bytes_to_unicode() -> dict[int, str]:
    bs = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {b: chr(c) for b, c in zip(bs, cs)}


def convert_npz_to_ct2(npz_path: Path, tiktoken_path: Path, out_dir: Path) -> Path:
    """Convert raw non-pickle OpenAI Whisper NPZ tensors into a CTranslate2 INT8 model."""
    tmp_out = out_dir.parent / f".building-{out_dir.name}-{os.getpid()}"
    shutil.rmtree(tmp_out, ignore_errors=True)
    tmp_out.mkdir(parents=True, exist_ok=True)

    w = np.load(str(npz_path), allow_pickle=False)
    n_enc_layers = int(w["dims/n_audio_layer"])
    n_enc_heads = int(w["dims/n_audio_head"])
    n_dec_layers = int(w["dims/n_text_layer"])
    n_dec_heads = int(w["dims/n_text_head"])
    n_vocab = int(w["dims/n_vocab"])

    spec = WhisperSpec(n_enc_layers, n_enc_heads, n_dec_layers, n_dec_heads)

    def arr(key: str) -> np.ndarray:
        return np.ascontiguousarray(w[f"params/{key}"], dtype=np.float32)

    def set_ln(ln_spec: object, prefix: str) -> None:
        ln_spec.gamma = arr(f"{prefix}.weight")
        ln_spec.beta = arr(f"{prefix}.bias")

    def set_lin(lin_spec: object, prefix: str, has_bias: bool = True) -> None:
        lin_spec.weight = arr(f"{prefix}.weight")
        if has_bias and f"params/{prefix}.bias" in w:
            lin_spec.bias = arr(f"{prefix}.bias")

    def set_attn(attn_spec: object, prefix: str, self_attn: bool = False) -> None:
        splits = [common_spec.LinearSpec() for _ in range(3)]
        set_lin(splits[0], f"{prefix}.query", has_bias=True)
        set_lin(splits[1], f"{prefix}.key", has_bias=False)
        set_lin(splits[2], f"{prefix}.value", has_bias=True)
        if self_attn:
            ct2_utils.fuse_linear(attn_spec.linear[0], splits)
        else:
            ct2_utils.fuse_linear(attn_spec.linear[0], splits[:1])
            ct2_utils.fuse_linear(attn_spec.linear[1], splits[1:])
        set_lin(attn_spec.linear[-1], f"{prefix}.out", has_bias=True)

    spec.encoder.conv1.weight = arr("encoder.conv1.weight")
    spec.encoder.conv1.bias = arr("encoder.conv1.bias")
    spec.encoder.conv2.weight = arr("encoder.conv2.weight")
    spec.encoder.conv2.bias = arr("encoder.conv2.bias")
    spec.encoder.position_encodings.encodings = arr("encoder.positional_embedding")
    set_ln(spec.encoder.layer_norm, "encoder.ln_post")
    for i in range(n_enc_layers):
        ls = spec.encoder.layer[i]
        set_attn(ls.self_attention, f"encoder.blocks.{i}.attn", self_attn=True)
        set_ln(ls.self_attention.layer_norm, f"encoder.blocks.{i}.attn_ln")
        set_lin(ls.ffn.linear_0, f"encoder.blocks.{i}.mlp.0")
        set_lin(ls.ffn.linear_1, f"encoder.blocks.{i}.mlp.2")
        set_ln(ls.ffn.layer_norm, f"encoder.blocks.{i}.mlp_ln")

    spec.decoder.position_encodings.encodings = arr("decoder.positional_embedding")
    spec.decoder.embeddings.weight = arr("decoder.token_embedding.weight")
    set_ln(spec.decoder.layer_norm, "decoder.ln")
    spec.decoder.projection.weight = arr("decoder.token_embedding.weight")
    for i in range(n_dec_layers):
        ls = spec.decoder.layer[i]
        set_attn(ls.self_attention, f"decoder.blocks.{i}.attn", self_attn=True)
        set_ln(ls.self_attention.layer_norm, f"decoder.blocks.{i}.attn_ln")
        set_attn(ls.attention, f"decoder.blocks.{i}.cross_attn", self_attn=False)
        set_ln(ls.attention.layer_norm, f"decoder.blocks.{i}.cross_attn_ln")
        set_lin(ls.ffn.linear_0, f"decoder.blocks.{i}.mlp.0")
        set_lin(ls.ffn.linear_1, f"decoder.blocks.{i}.mlp.2")
        set_ln(ls.ffn.layer_norm, f"decoder.blocks.{i}.mlp_ln")

    b2u = _bytes_to_unicode()
    ranks: dict[bytes, int] = {}
    with tiktoken_path.open("rb") as handle:
        for line in handle:
            line = line.strip()
            if line:
                tok_b64, rank_s = line.split()
                ranks[base64.b64decode(tok_b64)] = int(rank_s)

    vocab_dict: dict[str, int] = {}
    merges: list[tuple[str, str]] = []
    for token_bytes, rank in sorted(ranks.items(), key=lambda item: item[1]):
        vocab_dict["".join(b2u[b] for b in token_bytes)] = rank
        if len(token_bytes) >= 2:
            word = [bytes([b]) for b in token_bytes]
            while len(word) > 2:
                pairs = [
                    (ranks.get(a + b, 10**9), idx)
                    for idx, (a, b) in enumerate(zip(word, word[1:]))
                ]
                best_rank, merge_idx = min(pairs)
                if best_rank >= rank:
                    break
                word = (
                    word[:merge_idx]
                    + [word[merge_idx] + word[merge_idx + 1]]
                    + word[merge_idx + 2 :]
                )
            if len(word) == 2 and word[0] in ranks and word[1] in ranks:
                merges.append(("".join(b2u[b] for b in word[0]), "".join(b2u[b] for b in word[1])))

    special_tokens = [
        "<|endoftext|>",
        "<|startoftranscript|>",
        *[f"<|{lang}|>" for lang in WHISPER_LANGS_99],
        "<|translate|>",
        "<|transcribe|>",
        "<|startoflm|>",
        "<|startofprev|>",
        "<|nospeech|>",
        "<|notimestamps|>",
        *[f"<|{i * 0.02:.2f}|>" for i in range(1501)],
    ]

    tokenizer = Tokenizer(models.BPE(vocab=vocab_dict, merges=merges))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    tokenizer.add_special_tokens([AddedToken(t, special=True) for t in special_tokens])

    full_vocab: list[str] = [""] * n_vocab
    for key, idx in vocab_dict.items():
        full_vocab[idx] = key
    for offset, st in enumerate(special_tokens):
        full_vocab[len(vocab_dict) + offset] = st

    spec.config.suppress_ids = TINY_EN_SUPPRESS_IDS
    spec.config.suppress_ids_begin = [220, 50256]
    spec.config.lang_ids = list(range(50258, 50357))
    spec.config.alignment_heads = [[1, 0], [2, 0], [2, 5], [3, 0], [3, 1], [3, 2], [3, 3], [3, 4]]
    spec.register_vocabulary(full_vocab)
    spec.validate()
    spec.optimize(quantization="int8")
    spec.save(str(tmp_out))
    tokenizer.save(str(tmp_out / "tokenizer.json"))

    shutil.rmtree(out_dir, ignore_errors=True)
    tmp_out.rename(out_dir)
    return out_dir


def resolve_whisper_model_path(model_name: str, cache_dir: Path) -> tuple[str, str]:
    """Return `(resolved_model_path, canonical_model_label)` for `faster_whisper.WhisperModel`."""
    explicit_path = Path(model_name)
    if (explicit_path / "model.bin").is_file() and (explicit_path / "config.json").is_file():
        return str(explicit_path), explicit_path.name

    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_local = cache_dir / f"whisper-{model_name}-ct2"
    if (cached_local / "model.bin").is_file() and (cached_local / "config.json").is_file():
        return str(cached_local), f"whisper-{model_name}-ct2"

    # Try standard HuggingFace Hub download first on unrestricted hosts.
    try:
        from faster_whisper.utils import download_model

        downloaded = download_model(model_name, cache_dir=str(cache_dir))
        if downloaded and Path(downloaded, "model.bin").is_file():
            return str(downloaded), f"faster-whisper/{model_name}"
    except Exception as hf_err:
        logger.info(
            "HuggingFace Hub download unavailable (%s); checking GitHub weights bootstrap.",
            hf_err,
        )

    if model_name != "tiny.en":
        raise RuntimeError(
            f"Unable to download Whisper model {model_name!r} from HuggingFace Hub and only "
            "'tiny.en' supports offline/GitHub NPZ bootstrap."
        )

    with tempfile.TemporaryDirectory(prefix="whisper-bootstrap-") as tmp:
        clone_dir = Path(tmp) / "moonshine"
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                "https://github.com/moonshine-ai/useful-transformers.git",
                str(clone_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        subprocess.run(
            ["git", "-C", str(clone_dir), "sparse-checkout", "set", "examples/whisper"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        npz_path = clone_dir / "examples" / "whisper" / "weights" / "tiny.en.npz"
        tiktoken_path = clone_dir / "examples" / "whisper" / "assets" / "gpt2.tiktoken"
        built = convert_npz_to_ct2(npz_path, tiktoken_path, cached_local)
        return str(built), f"whisper-{model_name}-ct2"
