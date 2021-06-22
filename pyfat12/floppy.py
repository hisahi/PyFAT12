
import io


class FloppyImage:
    """Represents a floppy image.

    Attributes:
    capacity -- Capacity of the floppy drive in bytes.
    size -- Floppy size in inches, usually 3.5 or 5.25.
    bytes_per_sector -- Number of bytes per sector.
    """

    def __init__(self, size=3.5, capacity=1440):
        """Creates a new blank floppy image with no file system.

        Keyword arguments:
        size -- the size of the floppy that the image is for. (default 3.5, valid options 3.5 and 5.25)
        capacity -- the capacity of the floppy image in kilobytes (default 1440)
        """
        if size == 3.5:
            if capacity not in [360, 720, 1440]:
                raise ValueError(
                    f"{size} inch floppy images with {capacity} KB not supported"
                )
        elif size == 5.25:
            if capacity not in [360, 1200]:
                raise ValueError(
                    f"{size} inch floppy images with {capacity} KB not supported"
                )
        else:
            raise ValueError(f"{size} inch floppy images not supported")

        if size != 3.5 and capacity != 1440:
            raise NotImplementedError()

        self.size = size
        self.capacity = capacity * 1024
        self.bytes_per_sector = 512
        self._data = bytearray(self.capacity)

    @staticmethod
    def open(file):
        """Opens an existing floppy image.

        Arguments:
        file -- a file name or a file object (must be opened with 'rb'; will not be closed afterwards)
        """

        if isinstance(file, io.IOBase):
            self = FloppyImage.__new__(FloppyImage)
            self._data = bytearray(file.read())
            self.capacity = len(self._data)
            if self.capacity != 1440 * 1024:
                raise NotImplementedError()
            self.size = 3.5
            self.bytes_per_sector = 512
            return self
        elif isinstance(file, str):
            with open(file, "rb") as f:
                return FloppyImage.open(f)
        else:
            raise TypeError("file")

    def save(self, file):
        """Saves the floppy image into a file.

        Arguments:
        file -- a file name or a file object (must be opened with 'wb'; will not be closed afterwards)
        """

        if isinstance(file, io.IOBase):
            file.write(self._data)
        elif isinstance(file, str):
            with open(file, "wb") as f:
                self.save(f)
        else:
            raise TypeError("file")

    def read_sector(self, sectornum):
        """Reads a sector (512 bytes) from the floppy image.

        Arguments:
        sectornum -- the index of the sector (0 = first sector).
        """

        if (
            sectornum < 0
            or sectornum * self.bytes_per_sector >= len(self._data)
            or type(sectornum) != int
        ):
            raise ValueError("invalid sector index")

        return self.read(sectornum * self.bytes_per_sector, self.bytes_per_sector)

    def read_sectors(self, sectornum, sectorcount):
        """Reads sectors (512 bytes each) from the floppy image.

        Arguments:
        sectornum -- the index of the starting sector (0 = first sector).
        sectorcount -- number of sectors to read
        """

        if (
            sectornum < 0
            or (sectornum + sectorcount) * self.bytes_per_sector > len(self._data)
            or type(sectornum) != int
        ):
            raise ValueError("invalid sector index")

        return self.read(
            sectornum * self.bytes_per_sector, sectorcount * self.bytes_per_sector
        )

    def read(self, offset, length):
        """Reads data from the floppy image.

        Arguments:
        offset -- offset into floppy image
        length -- length of data to read
        """

        return self._data[offset: offset + length]

    def write_sector(self, sectornum, data):
        """Writes a sector (512 bytes) to the floppy image.

        Arguments:
        sectornum -- the number of the sector (0 = first sector).
        data -- sector data to write
        """

        if (
            sectornum < 0
            or sectornum * self.bytes_per_sector >= len(self._data)
            or type(sectornum) != int
        ):
            raise ValueError("invalid sector number")

        if len(data) != self.bytes_per_sector:
            raise ValueError("invalid sector length")

        self.write(sectornum * self.bytes_per_sector, data)

    def write_sectors(self, sectornum, sectorcount, data):
        """Writes a sector (512 bytes) to the floppy image.

        Arguments:
        sectornum -- the number of the sector (0 = first sector).
        sectorcount -- number of sectors to read
        data -- sector data to write
        """

        if (
            sectornum < 0
            or sectornum * self.bytes_per_sector >= len(self._data)
            or type(sectornum) != int
        ):
            raise ValueError("invalid sector number")

        if len(data) != sectorcount * self.bytes_per_sector:
            raise ValueError("invalid sector length")

        self.write(sectornum * self.bytes_per_sector, data)

    def write(self, offset, data):
        """Writes data to the floppy image.

        Arguments:
        offset -- offset into floppy image
        data -- data to write
        """

        self._data[offset: offset + len(data)] = data

    def read_mbr(self):
        """Reads the MBR (master boot record) from the floppy image."""
        return self.read_sector(0)

    def write_mbr(self, data):
        """Writes the MBR (master boot record) to the floppy image.

        Arguments:
        data -- MBR to write"""
        self.write_sector(0, data)
