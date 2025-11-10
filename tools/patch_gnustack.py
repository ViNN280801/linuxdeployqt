#!/usr/bin/env python3

from sys import argv as sys_argv
from sys import exit as sys_exit

from struct import pack as struct_pack
from struct import unpack as struct_unpack

# ELF Identification Constants
ELF_MAGIC_BYTES = b"\x7fELF"
ELF_CLASS_64 = 2  # EI_CLASS for 64-bit ELF
ELF_DATA_LSB = 1  # EI_DATA for little-endian

# Program Header Type
PT_GNU_STACK = 0x6474E551  # Segment type for GNU_STACK

# Program Header Flag Bits (p_flags)
PF_X = 0x1  # Execute bit
PF_W = 0x2  # Write bit
PF_R = 0x4  # Read bit

# Combined Permissions
RWX_PERMISSIONS = PF_R | PF_W | PF_X  # 0x7: Read, Write, Execute
RW_PERMISSIONS = PF_R | PF_W  # 0x6: Read, Write

# Offsets within Program Header Entry for p_flags
PH_FLAGS_OFFSET_64 = 4
PH_FLAGS_OFFSET_32 = 24

# Script Argument and Exit Codes
EXPECTED_ARGS_COUNT = 2
ERROR_EXIT_CODE = 1


class GnuStackPatcher:
    @staticmethod
    def fix_executable_stack(filename):
        with open(filename, "r+b") as f:
            elf = f.read()
            if elf[:4] != ELF_MAGIC_BYTES:
                print("Not an ELF file!")
                return

            is_64 = elf[4] == ELF_CLASS_64
            endian = "<" if elf[5] == ELF_DATA_LSB else ">"

            # Parse ELF header fields
            # e_phoff: offset of program headers
            e_phoff_offset = 32 if is_64 else 28
            e_phoff_size = 8 if is_64 else 4
            e_phoff = struct_unpack(
                endian + ("Q" if is_64 else "I"),
                elf[e_phoff_offset : e_phoff_offset + e_phoff_size],
            )[0]

            # e_phnum: number of program headers
            e_phnum_offset = 56 if is_64 else 44
            e_phnum_size = 2
            e_phnum = struct_unpack(
                endian + "H", elf[e_phnum_offset : e_phnum_offset + e_phnum_size]
            )[0]

            # e_phentsize: size of one program header
            e_phentsize_offset = 54 if is_64 else 42
            e_phentsize_size = 2
            e_phentsize = struct_unpack(
                endian + "H",
                elf[e_phentsize_offset : e_phentsize_offset + e_phentsize_size],
            )[0]

            found = False

            for i in range(e_phnum):
                phoff = e_phoff + i * e_phentsize

                if is_64:
                    p_type = struct_unpack(endian + "I", elf[phoff : phoff + 4])[0]
                    flags_off = phoff + PH_FLAGS_OFFSET_64
                    p_flags = struct_unpack(
                        endian + "I", elf[flags_off : flags_off + 4]
                    )[0]
                else:
                    p_type = struct_unpack(endian + "I", elf[phoff : phoff + 4])[0]
                    flags_off = phoff + PH_FLAGS_OFFSET_32
                    p_flags = struct_unpack(
                        endian + "I", elf[flags_off : flags_off + 4]
                    )[0]

                if p_type == PT_GNU_STACK:
                    print(
                        f"Found GNU_STACK at header #{i}, current flags: {hex(p_flags)}"
                    )
                    if (p_flags & RWX_PERMISSIONS) == RWX_PERMISSIONS:
                        with open(filename, "r+b") as wf:
                            wf.seek(flags_off)
                            wf.write(struct_pack(endian + "I", RW_PERMISSIONS))
                            print("Patched RWX -> RW-")
                            found = True
                    else:
                        print("Already not executable stack.")
                        found = True
            if not found:
                print("GNU_STACK segment not found.")


if __name__ == "__main__":
    if len(sys_argv) != EXPECTED_ARGS_COUNT:
        print(f"Usage: {sys_argv[0]} /path/to/lib<name>.so<[version]>")
        sys_exit(ERROR_EXIT_CODE)
    GnuStackPatcher.fix_executable_stack(sys_argv[1])
