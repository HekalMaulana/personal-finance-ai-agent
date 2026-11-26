"""Closed finance-only conversation; no model, tool registry, ledger or I/O."""
import re

_REFUSAL = 'Di luar cakupan. Saya hanya menangani keuangan pribadi. Ketik /finance bantuan.'
_LOCAL = ('Permintaan keuangan dikenali, tetapi akses ledger Telegram belum aktif. '
          'Gunakan CLI lokal untuk ledger uji fiktif; tidak ada data yang dibaca, disimpan, atau diekspor.')
_HELP = ('Simulasi — data fiktif saja. Gunakan Rupiah bulat tanpa pemisah:\n'
         '/finance arus-kas <pemasukan> <pengeluaran>\n'
         '/finance anggaran <pagu> <realisasi>\n'
         '/finance dana-darurat <pengeluaran-esensial-bulanan> <bulan>\n'
         '/finance target-tabungan <target> <saldo> <setoran-bulanan>\n'
         'Untuk pencatatan, ringkasan ledger atau laporan Excel, gunakan CLI lokal.')
_LEDGER_REQUESTS = frozenset({
    'catat pemasukan', 'catat pengeluaran', 'baca ringkasan transaksi', 'buat anggaran',
    'kelola target tabungan', 'minta analisis keuangan', 'buat laporan excel',
    '/finance catat', '/finance ringkasan', '/finance anggaran', '/finance tabungan', '/finance excel',
})
_AMOUNT = r'([0-9]{1,15})'
_SIMULATION = re.compile(
    rf'/finance (arus-kas|anggaran|dana-darurat|target-tabungan) {_AMOUNT} {_AMOUNT}(?: {_AMOUNT})?'
)


def reply_for_text(text: str) -> str:
    """Match complete inputs; never interpret embedded text or execute a tool call."""
    if type(text) is not str or len(text) > 128 or not text.isascii():
        return _REFUSAL
    text = text.lower()
    if text in ('/finance', '/finance bantuan'):
        return _HELP
    if text in _LEDGER_REQUESTS:
        return _LOCAL
    match = _SIMULATION.fullmatch(text)
    if match is None:
        return _REFUSAL
    kind, first, second, third = match.groups()
    if (kind == 'target-tabungan') != (third is not None):
        return _REFUSAL
    a, b = int(first), int(second)

    def rupiah(amount):
        return ('-' if amount < 0 else '') + f'Rp{abs(amount):,}'.replace(',', '.')

    if kind == 'arus-kas':
        result = f'Arus kas bersih = {rupiah(a)} − {rupiah(b)} = {rupiah(a - b)}.'
    elif kind == 'anggaran':
        result = f'Sisa pagu = {rupiah(a)} − {rupiah(b)} = {rupiah(a - b)}.'
    elif kind == 'dana-darurat':
        if not 1 <= b <= 120:
            return _REFUSAL
        result = f'Target dana darurat = {rupiah(a)}/bulan × {b} bulan = {rupiah(a * b)}.'
    else:
        assert third is not None  # Guaranteed by the input grammar above.
        contribution = int(third)
        if not contribution:
            return _REFUSAL
        remaining = max(0, a - b)
        months = (remaining + contribution - 1) // contribution
        result = (f'Sisa = maks(0, {rupiah(a)} − {rupiah(b)}) = {rupiah(remaining)}. '
                  f'Estimasi = {rupiah(remaining)} ÷ {rupiah(contribution)}/bulan, '
                  f'dibulatkan ke atas: {months} bulan tanpa bunga atau penarikan.')
    return f'Simulasi — data fiktif. {result} Tidak ada data yang disimpan.'
