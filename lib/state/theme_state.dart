import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ThemeState extends ChangeNotifier {
  static const _key = 'wavebook_light_mode';

  ThemeMode mode = ThemeMode.light;

  bool get isLight => mode == ThemeMode.light;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    mode = (prefs.getBool(_key) ?? true) ? ThemeMode.light : ThemeMode.dark;
    notifyListeners();
  }

  Future<void> setLight(bool light) async {
    mode = light ? ThemeMode.light : ThemeMode.dark;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_key, light);
  }
}
