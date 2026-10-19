import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api_client.dart';
import '../models/models.dart';

const String kAppVersion = '1.1.5';

int compareVersions(String a, String b) {
  final pa = a.split('.').map((s) => int.tryParse(s) ?? 0).toList();
  final pb = b.split('.').map((s) => int.tryParse(s) ?? 0).toList();
  final len = pa.length > pb.length ? pa.length : pb.length;
  for (var i = 0; i < len; i++) {
    final va = i < pa.length ? pa[i] : 0;
    final vb = i < pb.length ? pb[i] : 0;
    if (va != vb) return va - vb;
  }
  return 0;
}

Future<void> checkForUpdate(BuildContext context, {bool manual = false}) async {
  final messenger = ScaffoldMessenger.of(context);
  AppMeta meta;
  try {
    final data = await ApiClient().get('/api/app/meta', auth: false);
    meta = AppMeta.fromJson(data as Map<String, dynamic>);
  } catch (_) {
    if (manual) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Could not check for updates. Try again later.')),
      );
    }
    return;
  }

  final hasUpdate = meta.latestVersion.isNotEmpty &&
      compareVersions(meta.latestVersion, kAppVersion) > 0;
  if (!hasUpdate) {
    if (manual) {
      messenger.showSnackBar(
        SnackBar(content: Text('You are on the latest version ($kAppVersion).')),
      );
    }
    return;
  }
  if (!context.mounted) return;

  await showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text('Update available (v${meta.latestVersion})'),
      content: Text(
        meta.updateMessage.isNotEmpty
            ? meta.updateMessage
            : 'A new version of the WaveBook app is available.',
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Later')),
        if (meta.updateUrl.isNotEmpty)
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              launchUrl(Uri.parse(meta.updateUrl), mode: LaunchMode.externalApplication);
            },
            child: const Text('Update'),
          ),
      ],
    ),
  );
}
