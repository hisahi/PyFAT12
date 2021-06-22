
import datetime
import os
import struct
from . import path as fat12path


class FAT12:
    """Represents a FAT12 file system on a floppy image.

    Attributes.
    label -- Disk label. Read-only; use set_label to change.

    Attributes (should not be changed unless you know what you are doing):
    bytes_per_sector -- The number of bytes per disk sector.
    sectors_per_cluster -- The number of sectors per FAT cluster.
    fat_start_sector -- The index of the first sector containing the first FAT copy.
    fat_count -- The number of FAT copies, either 1 or (usually) 2.
    root_entries -- The number of entries the root directory can at most contain. Must be divisible by 16 and at most 240.
    logical_sectors -- The number of total logical sectors.
    descriptor -- The media descriptor. For floppy disks, this value should be 0xF0.
    sectors_per_fat -- The number of sectors each FAT copy takes.

    sectors_per_track -- The number of sectors per track.
    number_of_heads -- The number of drive heads (either 1 or 2).
    hidden_sectors -- The number of "hidden" sectors.
    large_total_logical_sectors -- The "large" number of total logical sectors. Not used for floppy disks.
    drive_number -- The drive number for this disk. Not used for floppy disks.
    ebpb_flags -- Unused EBPB byte.

    has_ebpb -- Whether the FAT contains an EBPB (extended BPB).
    bpb_label -- The label as stored in the EBPB (extended BIOS parameter block). Usually same as "label".
    serial -- The volume serial number, a 4 byte sequence.
    fs_type -- The file system type, always "FAT12   ".
    """

    def __init__(self, image):
        """Reads a FAT12 file system from a floppy image and returns it.

        Arguments:
        image -- the floppy image to act on
        """
        self._image = image
        self._readfs()

    @staticmethod
    def format(image, label="FloppyImage"):
        """Creates a new FAT12 file system into a floppy image and returns it.

        Arguments:
        image -- the floppy image to act on
        label -- the drive label
        """

        if image.size != 3.5 and image.capacity != 1440:
            raise NotImplementedError()

        try:
            label = label.encode("cp437")
        except:
            raise ValueError("label must be ASCII only")

        if len(label) > 11:
            raise ValueError("label is too long")
        elif len(label) < 11:
            label += b" " * (11 - len(label))

        vsn = os.urandom(4)
        mbr = bytearray(512)

        # initial code, vendor, BPB
        # 0000:7C00     EB 3C       JMP     SHOWMSG     [= 0000:7C3E]
        #               90          NOP

        mbr[
            :0x1C
        ] = b"\xeb\x3c\x90fat12.py\x00\x02\x01\x01\x00\x02\xe0\x00\x40\x0b\xf0\x09\0\x12\0\x02\0"
        # ext BPB
        mbr[0x26] = 0x29
        mbr[0x27: 0x27 + 4] = vsn
        mbr[0x2B: 0x2B + 11] = label
        mbr[0x36: 0x36 + 8] = b"FAT12   "

        # boot code (prints message)
        # 0000:7C3E             :SHOWMSG
        #               0E          PUSH    CS
        #               1F          POP     DS
        #               BE 5B 7C    MOV     SI, 7C5Bh
        # 0000:7C43             :NEXTCHAR
        #               AC          LODSB
        #               20 C0       AND     AL, AL
        #               74 0B       JE      KEYPRESS    [= 0000:7C53]
        #               56          PUSH    SI
        #               B4 0E       MOV     AH, 0Eh
        #               BB 07 00    MOV     BX, 0007h
        #               CD 10       INT     10h
        #               5E          POP     SI
        #               EB F0       JMP     NEXTCHAR    [= 0000:7C43]
        # 0000:7C53             :KEYPRESS
        #               31 C0       XOR     AX, AX
        #               CD 16       INT     16h
        # 0000:7C57             :REMBR
        #               CD 19       INT     19h
        #               EB FC       JMP     REMBR       [= 0000:7C57]

        mbr[
            0x3E: 0x3E + 29
        ] = b"\x0e\x1f\xbe\x5b\x7c\xac\x20\xc0\x74\x0b\x56\xb4\x0e\xbb\x07\x00\xcd\x10\x5e\xeb\xf0\x31\xc0\xcd\x16\xcd\x19\xeb\xfc"
        # message
        t = b"\r\nThis is not a bootable floppy.\r\nPlease remove this disk and press any key...\r\n\0"
        mbr[0x5B: 0x5B + len(t)] = t
        # ID
        mbr[0x1FE:0x200] = b"\x55\xaa"
        image.write_mbr(mbr)

        # FAT
        image.write(0x200, b"\xf0\xff\xff\x00")
        image.write(0x1400, b"\xf0\xff\xff\x00")
        # image.write(0x2600, label +
        #            b"\x28\0\0\0\0\0\0\0\0\0\0\x7c\xa1\x3a\x52\0\0\0\0\0\0")

        fat = FAT12(image)
        fat._write_label = True
        fat._updatelabel()
        return fat

    def _cluster_is_end_of_chain(self, cluster):
        return cluster & 0xFF8 == 0xFF8

    def _readbpb(self):
        image = self._image
        mbr = image.read_mbr()
        (
            bytes_per_sector,
            sectors_per_cluster,
            fat_start_sector,
            fat_count,
            root_entries,
            logical_sectors,
            descriptor,
            sectors_per_fat,
        ) = struct.unpack("<HBHBHHBH", mbr[0x0B:0x18])
        if fat_count not in [1, 2]:
            raise ValueError("invalid FAT count")
        if (
            bytes_per_sector != 512
            or sectors_per_cluster != 1
            or descriptor != 0xF0
            or root_entries % 16 != 0
        ):
            raise NotImplementedError()
        self.bytes_per_sector = bytes_per_sector
        self.sectors_per_cluster = sectors_per_cluster
        self.fat_start_sector = fat_start_sector
        self.fat_count = fat_count
        self.root_entries = root_entries
        self.logical_sectors = logical_sectors
        self.descriptor = descriptor
        self.sectors_per_fat = sectors_per_fat

        (
            sectors_per_track,
            number_of_heads,
            hidden_sectors,
            large_total_logical_sectors,
            drive_number,
            ebpb_flags,
        ) = struct.unpack("<HHIIBB", mbr[0x18:0x26])
        self.sectors_per_track = sectors_per_track
        self.number_of_heads = number_of_heads
        self.hidden_sectors = hidden_sectors
        self.large_total_logical_sectors = large_total_logical_sectors
        self.drive_number = drive_number
        self.ebpb_flags = ebpb_flags

        self.has_ebpb = mbr[0x26] == 0x29
        if self.has_ebpb:
            self.serial = mbr[0x27:0x2B]
            self.bpb_label = mbr[0x2B: 0x2B + 11]
            self.fs_type = mbr[0x36: 0x36 + 8]
            if self.fs_type not in [b"FAT     ", b"FAT12   "]:
                raise NotImplementedError()
        else:
            self.serial = None
            self.bpb_label = b" " * 11
            self.fs_type = None

    def _readfat(self):
        image = self._image
        # always read first FAT
        indx, cnt = self.fat_start_sector, self.sectors_per_fat
        data = image.read_sectors(indx, cnt)
        self._fat = []
        for i in range(0, len(data), 3):
            (pair,) = struct.unpack("<I", data[i: i + 3] + b"\0")
            self._fat.append(pair & 0xFFF)
            self._fat.append((pair >> 12) & 0xFFF)
        assert self._fat[0] == 0xFF0
        assert self._fat[1] == 0xFFF
        self._root_dir_sector = (
            self.fat_start_sector + self.sectors_per_fat * self.fat_count
        )
        self._first_cluster_sector = self._root_dir_sector + \
            (self.root_entries // 16)
        self._first_cluster_sector -= 2 * self.sectors_per_cluster
        self._first_cluster_sector = (
            self._first_cluster_sector + (self.sectors_per_cluster - 1)
        ) // self.sectors_per_cluster

    def _readfs(self):
        self._readbpb()
        self._readfat()
        self._readlabel()
        self._chdirroot()

    def _writebpb(self):
        assert self.root_entries % 16 == 0
        image = self._image
        image.write(
            0x0B,
            struct.pack(
                "<HBHBHHBH",
                self.bytes_per_sector,
                self.sectors_per_cluster,
                self.fat_start_sector,
                self.fat_count,
                self.root_entries,
                self.logical_sectors,
                self.descriptor,
                self.sectors_per_fat,
            ),
        )
        image.write(
            0x18,
            struct.pack(
                "<HHIIBB",
                self.sectors_per_track,
                self.number_of_heads,
                self.hidden_sectors,
                self.large_total_logical_sectors,
                self.drive_number,
                self.ebpb_flags,
            ),
        )
        if self.has_ebpb:
            assert len(self.serial) == 4
            assert self.fs_type in [b"FAT     ", b"FAT12   "]
            self.bpb_label = self._label
            image.write(0x27, self.serial)
            image.write(0x2B, self.bpb_label)
            image.write(0x36, self.fs_type)

    def _writefat(self):
        image = self._image
        assert len(self._fat) <= self.sectors_per_fat * \
            self.bytes_per_sector * 3 // 2
        if len(self._fat) & 1:
            self._fat.append(0)
        fats = bytearray(self.sectors_per_fat * self.bytes_per_sector)
        j = 0
        for i in range(0, len(self._fat), 2):
            fats[j: j + 3] = struct.pack(
                "<I", (self._fat[i] & 0xFFF) | (
                    (self._fat[i + 1] & 0xFFF) << 12)
            )[:3]
            j += 3
        image.write_sectors(
            self.fat_start_sector,
            self.sectors_per_fat * self.fat_count,
            fats * self.fat_count,
        )

    def commit(self):
        """Updates the file system (BPB and FATs) in the floppy image."""
        self._updatelabel()
        self._writebpb()
        self._writefat()

    def _cluster_index(self, cluster):
        return self._first_cluster_sector + cluster * self.sectors_per_cluster

    def _readcluster(self, cluster):
        return self._image.read_sectors(
            self._cluster_index(cluster), self.sectors_per_cluster
        )

    def _writecluster(self, cluster, data):
        self._image.write_sectors(
            self._cluster_index(cluster), self.sectors_per_cluster, data
        )

    # (head, tail)
    def _splitpath(self, path):
        path = path.replace("\\", "/")
        slash = path.find("/")
        if slash < 0:
            return (path, "")
        return (path[:slash], path[slash + 1:])

    def _efn_to_cfn(self, fn):
        if fn[0] == 5:
            fn[0] = 0xE5
        fn = fn.decode("cp437")
        ext = fn[8:].rstrip()
        if ext:
            fn = fn[:8].rstrip() + "." + ext
        else:
            fn = fn[:8].rstrip()
        return fn

    def _edt_to_pdt(self, dt):
        (i,) = struct.unpack("<I", dt)
        second = (i & 0x1F) * 2
        minute = (i >> 5) & 0x3F
        hour = (i >> 11) & 0x1F
        day = (i >> 16) & 0x1F
        month = (i >> 21) & 0x0F
        year = 1980 + ((i >> 25) & 0x7F)
        return datetime.datetime(year, month, day, hour, minute, second)

    def _pdt_to_edt(self, dt):
        year, month, day, hour, minute, second = (
            dt.year,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second // 2,
        )
        year, month, day, hour, minute, second = (
            (year - 1980) & 0x7F,
            month & 0x0F,
            day & 0x1F,
            hour & 0x1F,
            minute & 0x3F,
            second & 0x1F,
        )
        i = (
            (year << 25)
            | (month << 21)
            | (day << 16)
            | (hour << 11)
            | (minute << 5)
            | second
        )
        return struct.pack("<I", i)

    # (exists, filename, attributes, modified, cluster, file_size)
    #   exists = (True = file, False = free entry, None = end of directory)
    def _parsedirentry(self, data):
        if data[0] == 0:
            return (None, None, None, None, None, None)
        elif data[0] == 0xE5:
            return (False, None, None, None, None, None)
        return (
            True,
            self._efn_to_cfn(data[:0x0B]),
            data[0x0B],
            self._edt_to_pdt(data[0x16:0x1A]),
            struct.unpack("<H", data[0x1A:0x1C])[0],
            struct.unpack("<I", data[0x1C:0x20])[0],
        )

    def _makedirentry(self, filename, attributes, modified, cluster, file_size):
        if type(filename) == bytes:
            ext, filename = filename[8:], filename[:8]
        else:
            filename = filename.upper()
            if "." in filename:
                filename, ext = filename.rsplit(".", 1)
            else:
                filename, ext = filename, "   "
            filename = filename.encode("cp437")
            ext = ext.encode("cp437")
        if len(filename) > 8 or len(ext) > 3:
            raise ValueError("name too long")
        modified = datetime.datetime.now() if modified is None else modified
        if file_size < 0:
            raise ValueError("invalid file size")
        if cluster < 0 or cluster >= 0xFF6:
            raise ValueError("invalid starting cluster")
        return (
            filename.ljust(8)
            + ext.ljust(3)
            + bytearray([attributes, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
            + self._pdt_to_edt(modified)
            + struct.pack("<HI", cluster, file_size)
        )

    def _readlabel(self):
        self._write_label = False
        root_start, root_sectors, bpc = (
            self._root_dir_sector,
            self.root_entries // 16,
            self.bytes_per_sector,
        )
        rootdir = self._image.read_sectors(root_start, root_sectors)
        for i in range(0, len(rootdir), 32):
            if rootdir[i + 0x0B] & 8 == 8:
                # volume label
                self._label = rootdir[i: i + 11].decode("cp437").rstrip()
                return
        self._label = self.bpb_label.decode("cp437").rstrip()
        self.label = self._label

    def _updatelabel(self):
        if type(self._label) == str:
            self._label = self._label.encode("cp437")
        self._label = self._label[:11] + (
            b"\0" * (11 - len(self._label)) if len(self._label) < 11 else b""
        )
        root_start, root_sectors, bpc = (
            self._root_dir_sector,
            self.root_entries // 16,
            self.bytes_per_sector,
        )
        rootdir = self._image.read_sectors(root_start, root_sectors)
        if self._write_label:
            self._write_label = False
            if rootdir[0] not in [0, 0xE5] and rootdir[0x0B] & 8 == 8:
                rootdir[0:11] = self._label
            else:  # readd volume label if possible
                entries = []
                i = 0
                while i < len(rootdir) and rootdir[i] != 0:
                    entries.append(rootdir[i: i + 32])
                    i += 32
                if i < len(rootdir):
                    num_entries = len(entries)
                    entries = [
                        entry for entry in entries if entry[0x0B] & 0x0F == 8]
                    while len(entries) < num_entries:
                        entries.append(b"\0" * 32)
                    entries.insert(0, self._makedirentry(
                        self._label, 8, None, 0, 0))
                    if len(entries) * 32 <= len(rootdir):
                        for i, entry in enumerate(entries):
                            rootdir[i * 32: i * 32 + 32] = entry
            self._image.write_sectors(root_start, root_sectors, rootdir)

    def set_label(self, label):
        """Sets the label of this file system.

        Arguments:
        label -- The new disk label."""
        if type(label) == str:
            label = label.encode("cp437")
        label = label + (b" " * (11 - len(label)) if len(label) < 11 else b"")
        if len(label) > 11:
            raise ValueError("label too long")
        self.label, self._label = label, label
        self._write_label = True
        self.commit()

    # (filename, attributes, modified, cluster, file_size)
    def _allfilesin(self, sector, offset=0):
        assert offset % 32 == 0
        for i in range(offset, len(sector), 32):
            (
                exists,
                filename,
                attributes,
                modified,
                cluster,
                file_size,
            ) = self._parsedirentry(sector[i: i + 32])
            if exists is None:
                break
            if exists:
                if (
                    attributes & 0xC8 != 0
                ):  # volume label or device... or something else like that
                    continue
                yield (filename, attributes, modified, cluster, file_size)

    def _allocdirentrycluster(self, sector, offset=0):
        assert offset % 32 == 0
        for i in range(offset, len(sector), 32):
            if sector[i] not in [0x00, 0xE5]:
                continue
            return i
        return None

    def _allfilesincluster(self, cluster, offset=0):
        if cluster == 1:
            root_start, root_sectors, bps = (
                self._root_dir_sector,
                self.root_entries // 16,
                self.bytes_per_sector,
            )
            yield from self._allfilesin(
                self._image.read_sectors(root_start, root_sectors), offset
            )
        else:
            while not self._cluster_is_end_of_chain(cluster):
                yield from self._allfilesin(self._readcluster(cluster), offset)
                cluster = self._fat[cluster]
                offset = 0

    def _isvalidcluster(self, cluster):
        return 2 <= cluster < 0xFF0

    def _alloccluster(self, attach_to):
        if attach_to is not None:
            assert self._isvalidcluster(attach_to)
        # go through FAT
        for i in range(2, len(self._fat)):
            if self._fat[i] == 0:
                self._fat[i] = 0xFFF
                if attach_to:
                    self._fat[attach_to] = i
                return i
        raise IOError("floppy is full")

    # (orig_cluster, dir_cluster, dir_offset)
    def _allocdirentry(self, cluster, offset):
        if cluster == 1:  # root directory
            root_start, root_sectors, bps = (
                self._root_dir_sector,
                self.root_entries // 16,
                self.bytes_per_sector,
            )
            rootdir = self._image.read_sectors(root_start, root_sectors)
            noffset = self._allocdirentrycluster(rootdir, offset)
            if noffset is None:
                raise IOError("root directory is full")
            return (1, 1, noffset)
        else:
            ocluster = cluster
            pcluster = cluster
            while not self._cluster_is_end_of_chain(cluster):
                noffset = self._allocdirentrycluster(
                    self._readcluster(cluster), offset)
                if noffset is not None:
                    return (ocluster, cluster, noffset)
                pcluster = cluster
                cluster = self._fat[cluster]
                offset = 0
            if cluster is None or self._cluster_is_end_of_chain(cluster):
                # extend directory
                ncluster = self._alloccluster(pcluster)
                self._writecluster(
                    ncluster, bytes(self.bytes_per_sector *
                                    self.sectors_per_cluster)
                )
                return (ocluster, ncluster, 0)
            return (None, None, None)

    # (diroffset)
    def _resolvefilesector(self, name, sector, offset=0):
        assert offset % 32 == 0
        name = name.upper()
        for i in range(offset, len(sector), 32):
            (
                exists,
                filename,
                attributes,
                modified,
                cluster,
                file_size,
            ) = self._parsedirentry(sector[i: i + 32])
            if exists is None:
                break
            if exists:
                if (
                    attributes & 0xC8 != 0
                ):  # volume label or device... or something else like that
                    continue
                if filename.upper() == name:
                    return i
        return None

    # (diroffset)
    def _resolvedirsector(self, dir, sector, offset=0):
        assert offset % 32 == 0
        for i in range(offset, len(sector), 32):
            (
                exists,
                filename,
                attributes,
                modified,
                cluster,
                file_size,
            ) = self._parsedirentry(sector[i: i + 32])
            if exists is None:
                break
            if exists:
                if (
                    attributes & 0xC8 != 0
                ):  # volume label or device... or something else like that
                    continue
                if attributes & 0x10 == 0x10 and cluster == dir:
                    return i
        return None

    def _readdirentry(self, cluster, offset):
        if cluster == 1:  # root dir...
            root_start, root_sectors = self._root_dir_sector, self.root_entries // 16
            return self._image.read_sectors(root_start, root_sectors)[
                offset: offset + 32
            ]
        else:
            return self._readcluster(cluster)[offset: offset + 32]

    def _writedirentry(self, cluster, offset, entry):
        assert len(entry) == 32
        if cluster == 1:  # root dir...
            root_start, root_sectors = self._root_dir_sector, self.root_entries // 16
            rootdir = self._image.read_sectors(root_start, root_sectors)
            rootdir[offset: offset + 32] = entry
            self._image.write_sectors(root_start, root_sectors, rootdir)
        else:
            data = self._readcluster(cluster)
            data[offset: offset + 32] = entry
            self._writecluster(cluster, data)

    def _rmdirentry(self, cluster, offset, first_cluster):
        if cluster == 1:  # root dir...
            root_start, root_sectors = self._root_dir_sector, self.root_entries // 16
            rootdir = self._image.read_sectors(root_start, root_sectors)
            rootdir[offset] = 0xE5
            self._image.write_sectors(root_start, root_sectors, rootdir)
        else:
            data = self._readcluster(cluster)
            data[offset] = 0xE5
            self._writecluster(cluster, data)
            # maybe shorten directory?
            if all(cluster[i] in [0x00, 0xE5] for i in range(0, len(cluster), 32)):
                # impossible, first cluster in a subdir always has . and ..
                assert first_cluster != cluster
                prev_cluster = first_cluster
                while self._fat[prev_cluster] != cluster:
                    prev_cluster = self._fat[prev_cluster]
                self._fat[prev_cluster] = self._fat[cluster]
                self._fat[cluster] = 0

    # (dircluster, diroffset)
    def _resolvefile(self, name, cluster, offset=0):
        if cluster == 1:
            root_start, root_sectors, bps = (
                self._root_dir_sector,
                self.root_entries // 16,
                self.bytes_per_sector,
            )
            offset = self._resolvefilesector(
                name, self._image.read_sectors(
                    root_start, root_sectors), offset
            )
            if offset is None:
                return (None, None)
            return (1, offset)
        else:
            while not self._cluster_is_end_of_chain(cluster):
                offset = self._resolvefilesector(
                    name, self._readcluster(cluster), offset
                )
                if offset is not None:
                    return (cluster, offset)
                cluster = self._fat[cluster]
                offset = 0
            return (None, None)

    # (dircluster, diroffset)
    def _resolvedirbycluster(self, dir, cluster, offset=0):
        if cluster == 1:
            root_start, root_sectors, bps = (
                self._root_dir_sector,
                self.root_entries // 16,
                self.bytes_per_sector,
            )
            offset = self._resolvedirsector(
                dir, self._image.read_sectors(root_start, root_sectors), offset
            )
            if offset is None:
                return (None, None)
            return (1, offset)
        else:
            while not self._cluster_is_end_of_chain(cluster):
                offset = self._resolvedirsector(
                    dir, self._readcluster(cluster, offset))
                if offset is not None:
                    return (cluster, offset)
                cluster = self._fat[cluster]
                offset = 0
            return (None, None)

    # dircluster
    def _resolvedir(self, path, at_root):
        cluster = 1 if at_root else self._dircluster
        parents = [] if at_root else self._dirparents
        while path:
            name, path = self._splitpath(path)
            if not name and not path:
                break
            if not name:
                cluster = 1
                parents = []
                continue
            ocluster, offset = self._resolvefile(name, cluster)
            if ocluster is None:
                if cluster == 1 and name == ".":
                    continue
                return None, []
            entry = self._parsedirentry(self._readdirentry(ocluster, offset))
            if entry is None:
                return None, []
            parents.append(cluster)
            exists, filename, attributes, modified, cluster, file_size = entry
            if exists is not True:
                return None, []
            if attributes & 0x10 == 0:
                return None, []
            if cluster == 0:
                assert name in [".", ".."]
                if name == ".":
                    cluster = parents.pop()
                elif name == "..":
                    # parent
                    if parents:
                        parents.pop()
                        cluster = parents.pop()
                    else:
                        cluster = 1
        return cluster, parents

    # (dircluster, diroffset, fileoffset)
    def _resolvepath(self, path, at_root):
        cluster = 1 if at_root else self._dircluster
        parents = [] if at_root else self._dirparents
        ocluster, offset = None, None
        while path:
            name, path = self._splitpath(path)
            if not name and not path:
                break
            if not name:
                cluster = 1
                continue
            ocluster, offset = self._resolvefile(name, cluster)
            if ocluster is None:
                if cluster == 1 and name == ".":
                    continue
                return (None, None, None)
            if not path:
                # found a file
                return (cluster, ocluster, offset)
            entry = self._parsedirentry(self._readdirentry(ocluster, offset))
            if entry is None:
                return (None, None, None)
            exists, filename, attributes, modified, scluster, file_size = entry
            if exists is not True:
                return (None, None, None)
            if attributes & 0x10 == 0:
                return (None, None, None)
        if ocluster is None:
            return (None, None, None)
        return (cluster, ocluster, offset)

    def _isemptydir(self, dcluster):
        if dcluster == 1:
            return False
        i = 0
        for (
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) in self._allfilesincluster(dcluster):
            if i < 2 and filename[0] == ".":
                continue
            i += 1
            return False
        return True

    def _createfile(self, path, at_root):
        cluster = 1 if at_root else self._dircluster
        while path:
            name, path = self._splitpath(path)
            if not name and not path:
                break
            if not name:
                cluster = 1
                continue
            ocluster, offset = self._resolvefile(name, cluster)
            if not path:
                if ocluster is None:
                    # OK, good to go
                    break
                else:
                    raise ValueError("file already exists")
            if ocluster is None:
                if cluster == 1 and name == ".":
                    continue
                return (None, None, None)
            entry = self._parsedirentry(self._readdirentry(ocluster, offset))
            if entry is None:
                return (None, None, None)
            exists, filename, attributes, modified, scluster, file_size = entry
            if exists is not True:
                return (None, None, None)
            if attributes & 0x10 == 0:
                return (None, None, None)
        if name in [".", ".."]:
            raise ValueError("cannot create dotfile")
        now = datetime.datetime.now()
        direntry = self._makedirentry(name, 0x20, None, 0, 0)
        dcluster, ocluster, offset = self._allocdirentry(cluster, 0)
        self._writedirentry(ocluster, offset, direntry)
        return (cluster, ocluster, offset)

    def _createdirectory(self, path, at_root, chdir):
        path = path.replace("\\", "/")
        if path.endswith("/"):
            path = path[:-1]
        if not path:
            raise ValueError("cannot create root directory")
        ncluster = self._alloccluster(None)
        cluster, ocluster, offset = self._createfile(path, at_root)
        if cluster:
            name = fat12path.basename(path)
            self._writedirentry(
                ocluster, offset, self._makedirentry(
                    name, 16, None, ncluster, 0)
            )
            self._writedirentry(
                ncluster, 0, self._makedirentry(b".", 16, None, 0, 0))
            self._writedirentry(
                ncluster, 32, self._makedirentry(b"..", 16, None, 0, 0))
            if chdir:
                self._dircluster = ncluster
        return (cluster, ocluster, offset)

    def _chdirroot(self):
        self._dircluster, self._dirparents = 1, []

    def getdir(self):
        """Gets the path of the current directory."""
        tokens = []
        curdir = 1
        parents = iter(self._dirparents)

        while curdir != self._dircluster:
            nextdir = next(parents)
            dcluster, offset = self._resolvedirbycluster(nextdir, curdir)
            assert dcluster is not None
            tokens.append(self._parsedirentry(
                self._readdirentry(dcluster, offset))[1])
            curdir = nextdir

        return "/" + "/".join(tokens)

    def chdir(self, path):
        """Changes the current directory.

        Arguments:
        path -- the path to change to; / for root, .. for directory up
        """
        cluster, parents = self._resolvedir(path, False)
        if cluster is None:
            raise FileNotFoundError(path)
        self._dircluster = cluster
        self._dirparents = parents

    def listfiles(self, path, hidden=False):
        """Lists the files in a current directory.

        Arguments:
        path -- the path to list files in
        hidden -- show hidden files
        """
        cluster, parents = self._resolvedir(path, False)
        if cluster is None:
            raise FileNotFoundError(path)
        for (
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) in self._allfilesincluster(cluster):
            if attributes & 0x10 == 0 and (hidden or (attributes & 2) == 0):
                yield FAT12FileInfo(filename, attributes, modified, cluster, file_size)

    def listdirs(self, path, hidden=False):
        """Lists the directories in a current directory.

        Arguments:
        path -- the path to list directories in
        hidden -- show hidden directories
        """
        cluster, parents = self._resolvedir(path, False)
        if cluster is None:
            raise FileNotFoundError(path)
        for (
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) in self._allfilesincluster(cluster):
            if attributes & 0x10 != 0 and (hidden or (attributes & 2) != 0):
                yield FAT12FileInfo(filename, attributes, None, cluster, None)

    def stat(self, path):
        """Returns information about a file.

        Arguments:
        path -- the file path
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        if cluster is None:
            raise FileNotFoundError(path)
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(self._readdirentry(fcluster, foffset))
        is_dir = attributes & 0x10 != 0
        return FAT12FileInfo(
            filename,
            attributes,
            modified if not is_dir else None,
            cluster,
            file_size if not is_dir else None,
        )

    def _readfile(self, fcluster, foffset):
        bps = self.bytes_per_sector
        bpc = bps * self.sectors_per_cluster
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(self._readdirentry(fcluster, foffset))
        is_dir = attributes & 0x10 != 0
        if is_dir:
            raise ValueError("cannot read a directory")
        data = bytearray()
        for i in range(0, file_size, bpc):
            data += self._readcluster(cluster)[: file_size - i]
            cluster = self._fat[cluster]
        return data

    def read_file(self, path):
        """Reads and returns the contents of a file.

        Arguments:
        path -- the file path
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        if cluster is None:
            raise FileNotFoundError(path)
        return self._readfile(fcluster, foffset)

    def _writefile(self, fcluster, foffset, contents, ignore_readonly):
        bps = self.bytes_per_sector
        bpc = bps * self.sectors_per_cluster
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(self._readdirentry(fcluster, foffset))
        is_dir = attributes & 0x10 != 0
        if is_dir:
            raise ValueError("cannot write to a directory")
        if not ignore_readonly and attributes & 1 == 1:
            raise ValueError("file is read-only")

        # empty file?
        bpc = self.bytes_per_sector * self.sectors_per_cluster
        file_clusters = (file_size + (bpc - 1)) // bpc
        if cluster == 0:
            assert file_size == 0
            if not len(contents):
                return
            cluster = self._alloccluster(None)
            file_clusters = 1

        # last cluster of file
        lcluster = cluster
        while not self._cluster_is_end_of_chain(self._fat[lcluster]):
            lcluster = self._fat[lcluster]

        # new clusters to allocate?
        new_file_size = len(contents)
        new_file_clusters = (new_file_size + (bpc - 1)) // bpc
        for _ in range(file_clusters, new_file_clusters):
            lcluster = self._alloccluster(lcluster)

        # write data
        i, datacluster = 0, cluster
        for _ in range(new_file_clusters):
            assert self._isvalidcluster(datacluster)
            w = contents[i: i + bpc]
            if len(w) < bpc:
                w += (bpc - len(w)) * b"\0"
            self._writecluster(datacluster, w)
            i += bpc
            datacluster = self._fat[datacluster]

        # file keeps going?
        if file_clusters > new_file_clusters:
            while self._isvalidcluster(fcluster):
                # truncate, free extra clusters
                ncluster = self._fat[cluster]
                self._fat[cluster] = 0
                cluster = ncluster

        # update dir entry
        self._writedirentry(
            fcluster,
            foffset,
            self._makedirentry(filename, attributes, None,
                               cluster, new_file_size),
        )
        self.commit()

    def write_file(self, path, contents, ignore_readonly=False):
        """Writes the contents of a file. If the file does not exist, it will be created.

        Arguments:
        path -- the file path
        ignore_readonly -- ignores the read-only flag in the file (default: False)
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        if cluster is None:
            cluster, fcluster, foffset = self._createfile(path, False)
        if cluster is None:
            raise FileNotFoundError(path)
        self._writefile(fcluster, foffset, contents, ignore_readonly)

    def set_attributes(self, path, attrib):
        """Sets file attributes.

        Arguments:
        path -- the file path
        attrib -- The attribute flags. This is a bitfield with the following values:
            bit 0 (  1, 0x01) - read-only
            bit 1 (  2, 0x02) - hidden
            bit 2 (  4, 0x04) - system
            bit 4 ( 16, 0x10) - directory (not allowed through set_attributes)
            bit 5 ( 32, 0x20) - archive
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        bps = self.bytes_per_sector
        bpc = bps * self.sectors_per_cluster
        if cluster is None:
            raise FileNotFoundError(path)
        dcluster = cluster
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(self._readdirentry(fcluster, foffset))
        is_dir = attributes & 0x10 != 0

        if dcluster != 1 and filename in [".", ".."]:
            raise ValueError("cannot edit dotfile")

        attributes = (attributes & 0xD8) | (attrib & 0x27)
        self._writedirentry(
            fcluster,
            foffset,
            self._makedirentry(filename, attributes,
                               modified, cluster, file_size),
        )

    def delete_file(self, path, ignore_readonly=False):
        """Deletes a file.

        Arguments:
        path -- the file path
        ignore_readonly -- ignores the read-only flag in the file (default: False)
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        bps = self.bytes_per_sector
        bpc = bps * self.sectors_per_cluster
        if cluster is None:
            raise FileNotFoundError(path)
        dcluster = cluster
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(self._readdirentry(fcluster, foffset))
        is_dir = attributes & 0x10 != 0
        if is_dir:
            raise ValueError("cannot delete a directory with delete_file")
        if not ignore_readonly and attributes & 1 == 1:
            raise ValueError("file is read-only")

        if dcluster != 1 and filename in [".", ".."]:
            raise ValueError("cannot delete dotfile")

        # free clusters
        while self._isvalidcluster(cluster):
            ncluster = self._fat[cluster]
            self._fat[cluster] = 0
            cluster = ncluster

        # update dir entry
        self._rmdirentry(fcluster, foffset, cluster)
        self.commit()

    def create_directory(self, path, chdir=False):
        """Creates an (empty) directory.

        Arguments:
        path -- the file path
        chdir -- whether to change to newly created directory (default: False)
        """
        self._createdirectory(path, False, chdir)
        self.commit()

    def remove_directory(self, path):
        """Removes an (empty) directory.

        Arguments:
        path -- the file path
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        bps = self.bytes_per_sector
        bpc = bps * self.sectors_per_cluster
        if cluster is None:
            raise FileNotFoundError(path)
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(self._readdirentry(fcluster, foffset))
        is_dir = attributes & 0x10 != 0
        if not is_dir:
            raise ValueError("cannot delete a file with remove_directory")

        if not _isemptydir(cluster):
            raise ValueError("directory is not empty")

        if cluster == self._dircluster:
            self._chdirroot()

        # free clusters
        while self._isvalidcluster(cluster):
            ncluster = self._fat[cluster]
            self._fat[cluster] = 0
            cluster = ncluster

        # update dir entry
        self._rmdirentry(fcluster, offset)
        self.commit()

    def rename(self, path, name):
        """Renames an existing file.

        Arguments:
        path -- the file path
        name -- the new name
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        bps = self.bytes_per_sector
        bpc = bps * self.sectors_per_cluster
        if cluster is None:
            raise FileNotFoundError(path)
        dcluster = cluster
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(self._readdirentry(fcluster, foffset))
        is_dir = attributes & 0x10 != 0
        if dcluster != 1 and filename in [".", ".."]:
            raise ValueError("cannot rename dotfile")

        self._writedirentry(
            fcluster,
            foffset,
            self._makedirentry(name, attributes, modified, cluster, file_size),
        )

    def move(self, path, folder):
        """Moves an existing file to another folder.

        Arguments:
        path -- the file path
        folder -- the new folder
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        dcluster, parents = self._resolvedir(folder, False)
        bps = self.bytes_per_sector
        bpc = bps * self.sectors_per_cluster
        if cluster is None:
            raise FileNotFoundError(path)
        if dcluster is None:
            raise FileNotFoundError(folder)
        if cluster != 1 and filename in [".", ".."]:
            raise ValueError("cannot move dotfile")
        if cluster == dcluster:
            return
        oentry = self._readdirentry(fcluster, foffset)
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(oentry)
        is_dir = attributes & 0x10 != 0

        if is_dir and cluster == self._dircluster:
            self._chdirroot()

        dcluster, ocluster, offset = self._allocdirentry(cluster, 0)
        self._writedirentry(ocluster, offset, oentry)
        self._rmdirentry(fcluster, foffset, cluster)
        self.commit()

    def exists(self, path):
        """Checks whether a file or directory exists at a given path.

        Arguments:
        path -- The file path.
        """
        scluster, sfcluster, sfoffset = self._resolvepath(path, False)
        return scluster is not None

    def isfile(self, path):
        """Checks whether a file exists at a given path.

        Arguments:
        path -- The file path.
        """
        cluster, fcluster, foffset = self._resolvepath(path, False)
        if cluster is None:
            return False
        else:
            (
                exists,
                filename,
                attributes,
                modified,
                cluster,
                file_size,
            ) = self._parsedirentry(self._readdirentry(fcluster, foffset))
            return attributes & 0x10 == 0

    def isdir(self, path):
        """Checks whether a directory exists at a given path.

        Arguments:
        path -- The file path.
        """
        d = self._resolvedir(path, False)
        return d is not None and d[0] is not None

    def issamefile(self, path1, path2):
        """Resolves both paths and checks whether they resolve to the same file.

        Arguments:
        path1 -- The first path.
        path2 -- The second path.

        Returns None if either path fails to resolve.
        """
        scluster, sfcluster, sfoffset = self._resolvepath(path1, False)
        dcluster, dfcluster, dfoffset = self._resolvepath(path2, False)
        if sfcluster is None or dfcluster is None:
            return None
        return sfcluster == dfcluster and sfoffset == dfoffset

    def copy(self, source, destination, ignore_readonly=False):
        """Copies an existing file to another folder.

        Arguments:
        source -- the file to copy
        destination -- the destination file or folder
        ignore_readonly -- ignores the read-only flag in the destination file if it exists (default: False)
        """
        scluster, sfcluster, sfoffset = self._resolvepath(source, False)
        dcluster, dfcluster, dfoffset = self._resolvepath(destination, False)
        if scluster is None:
            raise FileNotFoundError(source)
        if sfcluster == dfcluster and sfoffset == dfoffset:
            raise ValueError("cannot copy file to itself")
        if dcluster is None:
            dcluster, dfcluster, dfoffset = self._createfile(
                destination, False)
        if dcluster is None:
            raise FileNotFoundError(destination)
        (
            exists,
            filename,
            attributes,
            modified,
            cluster,
            file_size,
        ) = self._parsedirentry(self._readdirentry(sfcluster, sfoffset))
        dattributes = self._parsedirentry(
            self._readdirentry(dfcluster, dfoffset))[2]
        if dattributes & 0x10 == 0x10:  # directory
            dcluster, dfcluster, dfoffset = self._createfile(
                fat12path.join(
                    destination, fat12path.basename(source)), at_root
            )
        if not ignore_readonly and dattributes & 1 == 1:
            raise ValueError("destination file is read-only")
        self._writedirentry(
            dfcluster,
            dfoffset,
            self._makedirentry(
                fat12path.basename(
                    destination), attributes | 0x20 & ~0x04, None, 0, 0
            ),
        )
        self._writefile(dfcluster, dfoffset, self._readfile(
            sfcluster, sfoffset), True)


class FAT12FileInfo:
    """Contains information about a file in a FAT12 file system.

    Attributes:
    name -- The name of this file.
    attributes -- The attributes of this file. This is a bitfield with the following values:
            bit 0 (  1, 0x01) - read-only
            bit 1 (  2, 0x02) - hidden
            bit 2 (  4, 0x04) - system
            bit 4 ( 16, 0x10) - directory
            bit 5 ( 32, 0x20) - archive
    date -- The modification date of this file.
    size -- The size of this file in bytes.
    starting_cluster -- The first FAT cluster to contain the contents of this file.
    """

    def __init__(self, name, attributes, date, cluster, size):
        self.name, self.attributes, self.date, self.starting_cluster, self.size = (
            name,
            attributes,
            date,
            cluster,
            size,
        )

    def __repr__(self):
        return f'<"{self.name}", {self.size}>'
