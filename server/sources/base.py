from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from server.models import Olay, Paket, Sinyal


class Kaynak(ABC):
    """Veri ureten her kaynak (mock, ileride yolo, simulator) bu arayuzu uygular.

    Kaynak sunucunun icini bilmez; urettigini verilen fonksiyonlara teslim eder.
    Mesajlar sifreli `Paket` olarak gelir, cozmek sunucunun isi.
    """

    @abstractmethod
    async def calistir(
        self,
        olay: Callable[[Olay], Awaitable[None]],
        paket: Callable[[Paket], Awaitable[None]],
        sinyal: Callable[[Sinyal], Awaitable[None]],
    ): ...

    async def olay_bildir(self, olay: Olay):
        """Sunucuya bir olay geldi (kaynaktan ya da HTTP'den). Simulasyon dugumleri acil moda alabilir."""
