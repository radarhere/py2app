import os
import sys

import PIL.Image

PATH = "/System/Library//Automator/Crop Images.action/Contents/Resources/shark-tall-no-scale.jpg"

print("globals() is %r" % id(globals()))


def somefunc():
    print("globals() is %r" % id(globals()))
    print("Hello from py2app")

    print("frozen", repr(getattr(sys, "frozen", None)))

    print("sys.path", sys.path)
    print("sys.executable", sys.executable)
    print("sys.prefix", sys.prefix)
    print("sys.argv", sys.argv)
    print("os.getcwd()", os.getcwd())


if __name__ == "__main__":
    somefunc()
    with PIL.Image.open(PATH) as img:
        print(type(img))
        print(img.size)
