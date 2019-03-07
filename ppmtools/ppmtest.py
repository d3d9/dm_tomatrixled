from PIL import Image, ImageFile
from image_to_ansi import rgb2short
from sys import argv

ImageFile.LOAD_TRUNCATED_IMAGES = True
colors = {}
filename = argv[1] if len(argv) > 1 else '/tmp/out.ppm'

with open(filename, 'rb') as f:
    while True:
        s = False
        while not s:
            try:
                im = Image.open(f)
            except Exception as e:
                print(e)
            else:
                s = True
        _ppmstr = ""
        for y in range(im.size[1]):
            for x in range(im.size[0]):
                p = im.getpixel((x,y))
                h = "%2x%2x%2x" % (p[0],p[1],p[2])
                short = colors.get(h)
                if short is None:
                    short = rgb2short(h)[0]
                    colors[h] = short
                _ppmstr += "\033[48;5;%sm  " % short
            _ppmstr += "\033[0m\n"
        _ppmstr += "\n"
        print(_ppmstr)

