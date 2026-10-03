"""CPU English -> Russian translation, independent of public API quotas.

Argos/OpenNMT model: https://github.com/argosopentech/argospm-index
Inference: https://opennmt.net/CTranslate2/translation.html
"""
import hashlib
import io
import os
import re
from pathlib import Path
import zipfile

MODEL_URL = 'https://argos-net.com/v1/translate-en_ru-1_9.argosmodel'
MODEL_SHA256 = '591d743ae103752b88ffc38785c50421320f4eff93c8967e0d3d2e14d4e27811'
MODEL_ROOT = Path('.translation-model/translate-en_ru-1_9')
_engine = None
_tokenizer = None


def enabled():
    return bool(os.environ.get('LOCAL_TRANSLATION_MODEL'))


def install():
    """Download once; Actions caches the verified model between runs."""
    if (MODEL_ROOT / 'model/model.bin').is_file() and (MODEL_ROOT / 'sentencepiece.model').is_file():
        return
    import requests
    response = requests.get(MODEL_URL, timeout=180)
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != MODEL_SHA256:
        raise RuntimeError('Translation model checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        root = MODEL_ROOT.parent.resolve()
        for name in archive.namelist():
            if not (root / name).resolve().is_relative_to(root):
                raise RuntimeError('Unsafe translation model archive path')
        archive.extractall(root)
    print('Installed verified English -> Russian translation model')


def _translate(chunk):
    global _engine, _tokenizer
    if _engine is None:
        import ctranslate2
        import sentencepiece
        root = Path(os.environ['LOCAL_TRANSLATION_MODEL'])
        _tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(root / 'sentencepiece.model'))
        _engine = ctranslate2.Translator(str(root / 'model'), device='cpu', compute_type='int8', intra_threads=2)
    tokens = _tokenizer.encode(chunk, out_type=str)
    result = _engine.translate_batch([tokens], beam_size=4, replace_unknowns=True,
                                    max_input_length=0, max_decoding_length=1024)[0]
    text = _tokenizer.decode(result.hypotheses[0]).strip()
    return re.sub(r'_+KEEP_(\d+)_+', lambda m: '__KEEP_' + m[1] + '__', text)


def translate(chunk):
    result = _translate(chunk)
    tokens = re.findall(r'__KEEP_\d+__', chunk)
    # Some title-cased English headlines are copied verbatim by the model.
    # Sentence-case the prose on retry; protected names keep their spelling.
    prose = re.sub(r'__KEEP_\d+__', '', result)
    cyr = len(re.findall('[А-Яа-яЁё]', prose))
    latin = len(re.findall('[A-Za-z]', prose))
    if cyr < 2 or (cyr < 30 and cyr < latin * .55) or 'Оригинальное название:' in result:
        normalized = re.sub(r'__KEEP_\d+__|[A-Za-z]+',
                            lambda m: m[0] if m[0].startswith('__KEEP_') else m[0].lower(), chunk)
        result = _translate(normalized)
    if all(result.count(token) == chunk.count(token) for token in tokens):
        return result
    # NMT can omit an unfamiliar name token, especially in headlines. Retry
    # the surrounding prose separately rather than losing any named entity.
    pieces = re.split(r'(__KEEP_\d+__)', chunk)
    translated = []
    for piece in pieces:
        if re.fullmatch(r'__KEEP_\d+__', piece) or not re.search('[A-Za-z]', piece):
            translated.append(piece)
        else:
            translated.append(_translate(piece.strip()))
    return ' '.join(piece.strip() for piece in translated if piece.strip())


if __name__ == '__main__':
    install()
