"""Avatar redondo.

Era um QLabel com `border-radius` no stylesheet e a foto em setPixmap.
Qt NAO recorta pixmap pelo border-radius: desenha a caixa arredondada e
estampa a imagem quadrada por cima, sem clipe -- o avatar saia quadrado.
E ficava deslocado porque a borda de 1px encolhe a area de conteudo e o
QLabel centrava a imagem nessa area menor, nao no circulo.
"""
from __future__ import annotations

import pytest

from PyQt6.QtGui import QColor, QPixmap
from skinvault.ui.components import Avatar


@pytest.fixture(autouse=True)
def app():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    inst = QApplication.instance() or QApplication([])
    yield inst
    for w in list(inst.topLevelWidgets()):
        w.deleteLater()
    inst.processEvents()
    inst.quit()


def _foto(cor="#FF0000", lado=184):
    """Pixmap chapado, pra distinguir "e' foto" de "nao e' foto"."""
    px = QPixmap(lado, lado)
    px.fill(QColor(cor))
    buf = px.toImage()
    from PyQt6.QtCore import QBuffer, QByteArray
    ba = QByteArray()
    b = QBuffer(ba)
    b.open(QBuffer.OpenModeFlag.WriteOnly)
    buf.save(b, "PNG")
    return bytes(ba)


def _cor(widget, x, y):
    c = QColor(widget.grab().toImage().pixel(x, y))
    return (c.red(), c.green(), c.blue())


def test_canto_nao_recebe_a_foto(app):
    """O canto do quadrado esta' FORA do circulo -- e era ali que a foto
    vazava."""
    a = Avatar(72)
    a.set_image(_foto("#FF0000"))
    assert _cor(a, 2, 2) != (255, 0, 0)
    assert _cor(a, 69, 2) != (255, 0, 0)
    assert _cor(a, 2, 69) != (255, 0, 0)
    assert _cor(a, 69, 69) != (255, 0, 0)


def test_centro_recebe_a_foto(app):
    a = Avatar(72)
    a.set_image(_foto("#FF0000"))
    assert _cor(a, 36, 36) == (255, 0, 0)


def test_foto_cobre_o_circulo_inteiro(app):
    """Perto da borda, ainda dentro do circulo, tem que haver foto -- se
    houvesse fundo ali, a imagem estaria menor que o circulo."""
    a = Avatar(72)
    a.set_image(_foto("#FF0000"))
    assert _cor(a, 36, 6) == (255, 0, 0)     # topo, no eixo vertical
    assert _cor(a, 6, 36) == (255, 0, 0)     # esquerda, no eixo horizontal


def test_sem_foto_mostra_a_inicial(app):
    a = Avatar(72)
    a.set_initials("nokia")
    assert a.text() == "N"


def test_foto_vence_a_inicial(app):
    """Chamar set_initials depois da foto nao pode apagar a foto."""
    a = Avatar(72)
    a.set_image(_foto("#00FF00"))
    a.set_initials("nokia")
    assert _cor(a, 36, 36) == (0, 255, 0)


def test_sem_nome_fica_o_interrogacao(app):
    a = Avatar(72)
    a.set_initials("")
    assert a.text() == "?"


def test_dado_invalido_nao_quebra(app):
    a = Avatar(72)
    a.set_image(b"isto nao e' uma imagem")
    a.set_image(None)
    assert a.pixmap() is None
