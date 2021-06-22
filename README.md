
# PyFAT12

PyFAT12 is a Python 3 library that allows handling FAT12 file systems. FAT12,
or original FAT, is a file system designed by Microsoft that was used primarily
on 5.25-inch and 3.5-inch floppy disks.

Currently PyFAT12 supports 3.5-inch high density (1.44 MB) floppy disk images
and handling any FAT12 file systems on them. It is also possible to format
a new FAT12 volume. Files can be opened, overwritten, created, renamed, deleted
and so on; subdirectory and volume label support is also present.

This library has not been tested extensively, but basic functionality appears
to work. There might still be bugs.

## Installation

PyFAT12 has been tested on recent Python 3 versions and does not require
any libraries beyond the standard library Python comes with.

```
pip install pyfat12
```

## Documentation

The library comes with docstrings which can be viewed with `help`. Currently
no documentation exists other than this README and the docstrings, but there
are plans to improve the situation.

## Examples

The following example creates a new 3.5-inch high density (1.44 MB) floppy
image called `DISK1.IMG` in the current directory. The image contains a blank,
formatted FAT12 file system:

```python3
from pyfat12 import FloppyImage, FAT12
floppy = FloppyImage()
fs = FAT12.format(floppy, "Disk label")
floppy.save("DISK1.IMG")
```

Opening up an existing image and lists all files from its root directory:

```python3
from pyfat12 import FloppyImage, FAT12
floppy = FloppyImage.open("DISK1.IMG")
fs = FAT12(floppy)
fileCount = 0

for file in fs.listfiles("/"):
    fileCount += 1
    print(file.name, file.size)

print(fileCount, "files in total")
```

Opening up an existing image, adding a new file (or overwriting an existing
one) and saving:

```python3
from pyfat12 import FloppyImage, FAT12
floppy = FloppyImage.open("DISK1.IMG")
fs = FAT12(floppy)
fs.write_file("/HELLO.TXT", b"Hello World!\r\n")
floppy.save("DISK1.IMG")
```

## License

MIT License. See `LICENSE`.
