import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../models/models.dart';
import '../theme.dart';

Future<void> confirmAndLogout(BuildContext context) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Log out?'),
      content: const Text('You will need to sign in again to manage your business.'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
        TextButton(
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Log out', style: TextStyle(color: WaveBookColors.danger)),
        ),
      ],
    ),
  );
  if (ok != true || !context.mounted) return;
  await context.read<AuthState>().logout();
}

class AuthState extends ChangeNotifier {
  final ApiClient api = ApiClient();

  User? user;
  bool loading = false;
  String? error;

  bool get isLoggedIn => user != null;
  bool get hasBusiness => user?.businessId != null;

  Future<bool> restoreSession() async {
    try {
      final me = await api.get('/api/auth/me');
      user = User.fromJson(me as Map<String, dynamic>);
      notifyListeners();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> login(String email, String password) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final data = await api.post('/api/auth/login', body: {
        'email': email,
        'password': password,
      });
      await api.saveToken(data['access_token'] as String);
      user = User.fromJson(data['user'] as Map<String, dynamic>);
      return true;
    } on ApiException catch (e) {
      error = e.message;
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<bool> signup(String email, String password, String fullName, String phone) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final data = await api.post('/api/auth/signup', body: {
        'email': email,
        'password': password,
        'full_name': fullName,
        'phone': phone,
      });
      await api.saveToken(data['access_token'] as String);
      user = User.fromJson(data['user'] as Map<String, dynamic>);
      return true;
    } on ApiException catch (e) {
      error = e.message;
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    await api.clearToken();
    user = null;
    notifyListeners();
  }

  void refreshUser(User updated) {
    user = updated;
    notifyListeners();
  }
}
