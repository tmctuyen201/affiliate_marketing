from pathlib import Path

_src_pkg = Path(__file__).resolve().parent.parent / 'src' / 'affiliate_agent'
__path__ = [str(_src_pkg)]
