import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("inventory_embedded_amdgpu_elf.py")
SPEC = importlib.util.spec_from_file_location("shader_inventory", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def synthetic_elf(machine=0xE0, truncate=False):
    strings = b"\0.shstrtab\0.shader_header\0.shader_text\0"
    shoff = 0x80
    stroff = 0x180
    textoff = 0x200
    blob = bytearray(0x220)
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    header = MODULE.ELF64_HEADER.pack(
        ident, 1, machine, 1, 0, 0, shoff, 0, 64, 0, 0, 64, 4, 1
    )
    blob[:64] = header
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (1, 3, 0, 0, stroff, len(strings), 0, 0, 1, 0),
        (11, 1, 0, 0, textoff, 8, 0, 0, 4, 0),
        (26, 1, 0, 0, textoff + 8, 8, 0, 0, 4, 0),
    ]
    for index, section in enumerate(sections):
        MODULE.ELF64_SECTION.pack_into(blob, shoff + index * 64, *section)
    blob[stroff:stroff + len(strings)] = strings
    if truncate:
        return bytes(blob[:0x190])
    return bytes(blob)


class ShaderInventoryTests(unittest.TestCase):
    def scan(self, blob):
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(blob)
            handle.flush()
            return MODULE.inventory(Path(handle.name))

    def test_valid_shader_pair_is_classified(self):
        record = self.scan(b"prefix" + synthetic_elf())
        self.assertEqual(record["elf_magic_count"], 1)
        self.assertEqual(record["amdgpu_elf_count"], 1)
        self.assertEqual(record["amdgpu_shader_pair_count"], 1)
        self.assertTrue(record["amdgpu_candidates"][0]["has_shader_pair"])

    def test_magic_and_machine_without_valid_tables_is_rejected(self):
        fake = bytearray(64)
        fake[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", fake, 18, 0xE0)
        record = self.scan(bytes(fake))
        self.assertEqual(record["elf_magic_count"], 1)
        self.assertEqual(record["amdgpu_elf_count"], 0)

    def test_truncated_section_payload_is_rejected(self):
        record = self.scan(synthetic_elf(truncate=True))
        self.assertEqual(record["amdgpu_elf_count"], 0)

    def test_non_amdgpu_elf_is_rejected(self):
        record = self.scan(synthetic_elf(machine=0x3E))
        self.assertEqual(record["amdgpu_elf_count"], 0)


if __name__ == "__main__":
    unittest.main()
