import 'package:flutter/material.dart';

import '../theme.dart';

class LoadingNetworkImage extends StatelessWidget {
  final String url;
  final double? width;
  final double? height;
  final BoxFit fit;
  final double iconSize;

  const LoadingNetworkImage({
    super.key,
    required this.url,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
    this.iconSize = 48,
  });

  @override
  Widget build(BuildContext context) {
    return Image.network(
      url,
      width: width,
      height: height,
      fit: fit,
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return _Placeholder(
          width: width,
          height: height,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              if (height == null || height! >= 96) ...[
                const SizedBox(height: 8),
                const Text(
                  'Loading image, please wait',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 11, color: WaveBookColors.muted),
                ),
              ],
            ],
          ),
        );
      },
      errorBuilder: (_, _, _) => _Placeholder(
        width: width,
        height: height,
        child: Icon(Icons.image, size: iconSize, color: WaveBookColors.muted),
      ),
    );
  }
}

class _Placeholder extends StatelessWidget {
  final double? width;
  final double? height;
  final Widget child;

  const _Placeholder({this.width, this.height, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      alignment: Alignment.center,
      padding: const EdgeInsets.all(4),
      color: WaveBookColors.muted.withValues(alpha: 0.08),
      child: child,
    );
  }
}
