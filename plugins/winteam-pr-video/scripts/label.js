// Usage: osascript -l JavaScript label.js "<text>" <out.png> [width] [height]
// Renders a white-on-dark label PNG with AppKit (Homebrew's ffmpeg has no drawtext filter).
ObjC.import('AppKit');

function run(argv) {
  const text = argv[0], out = argv[1], w = Number(argv[2] || 540), h = Number(argv[3] || 64);
  const rep = $.NSBitmapImageRep.alloc.initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
    null, w, h, 8, 4, true, false, 'NSDeviceRGBColorSpace', 0, 0);
  $.NSGraphicsContext.saveGraphicsState;
  $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep));
  $.NSColor.colorWithCalibratedRedGreenBlueAlpha(0.1, 0.1, 0.1, 1).setFill;
  $.NSRectFill($.NSMakeRect(0, 0, w, h));
  const attrs = $.NSMutableDictionary.alloc.init;
  attrs.setObjectForKey($.NSFont.boldSystemFontOfSize(Math.round(h * 0.4)), $.NSFontAttributeName);
  attrs.setObjectForKey($.NSColor.whiteColor, $.NSForegroundColorAttributeName);
  const s = $.NSString.alloc.initWithUTF8String(text);
  const size = s.sizeWithAttributes(attrs);
  s.drawAtPointWithAttributes($.NSMakePoint((w - size.width) / 2, (h - size.height) / 2), attrs);
  $.NSGraphicsContext.restoreGraphicsState;
  rep.representationUsingTypeProperties(4 /* PNG */, $()).writeToFileAtomically(out, true);
}
