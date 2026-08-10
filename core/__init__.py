"""O'zbek ovozli AI-assistent yadrosi.

Bu paket audio manbadan (mikrofon, brauzer, kelajakda Asterisk AudioSocket)
mustaqil: unga faqat 16 kHz PCM mono bo'laklar oqimi kerak.
"""

from core.config import Settings
from core.pipeline import AssistantPipeline

__all__ = ["Settings", "AssistantPipeline"]
