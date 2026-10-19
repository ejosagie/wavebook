import 'package:flutter/material.dart';

/// Currency symbol for a business's display currency (defaults to GBP).
String currencySymbol(String code) {
  switch (code.toUpperCase()) {
    case 'USD':
      return r'$';
    case 'CAD':
      return r'C$';
    case 'EUR':
      return '€';
    case 'AUD':
      return r'A$';
    case 'NZD':
      return r'NZ$';
    case 'NGN':
      return '₦';
    case 'KES':
      return 'KSh';
    case 'ZAR':
      return 'R';
    default:
      return '£';
  }
}

class WaveBookColors {
  // Pink beauty palette
  static const pink = Color(0xFFEC4899);
  static const pinkDark = Color(0xFFDB2777);
  static const pinkLight = Color(0xFFF9A8D4);
  static const rose = Color(0xFFBE185D);
  static const blush = Color(0xFFFDF2F8);

  // Dark surfaces
  static const darkBg = Color(0xFF121014);
  static const darkSurface = Color(0xFF1C1920);
  static const darkSurfaceAlt = Color(0xFF262129);
  static const darkBorder = Color(0xFF332C36);

  // Neutrals
  static const ink = Color(0xFF1C1917);
  static const lightBg = Color(0xFFFFF5F9);
  static const lightBorder = Color(0xFFF0D3E2);
  static const muted = Color(0xFF8B8494);
  static const white = Color(0xFFFFFFFF);
  static const bgSoft = Color(0xFFF5F0F4);

  static const success = Color(0xFF34D399);
  static const danger = Color(0xFFF87171);
  static const warning = Color(0xFFFBBF24);

  static const gradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFFEC4899), Color(0xFFA855F7)],
  );
}

ThemeData buildWaveBookTheme({Brightness brightness = Brightness.dark}) {
  final isDark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: WaveBookColors.pink,
    brightness: brightness,
    primary: WaveBookColors.pink,
    secondary: WaveBookColors.rose,
    surface: isDark ? WaveBookColors.darkSurface : Colors.white,
  );
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: isDark ? WaveBookColors.darkBg : WaveBookColors.lightBg,
    appBarTheme: AppBarTheme(
      backgroundColor: isDark ? WaveBookColors.darkBg : WaveBookColors.lightBg,
      foregroundColor: isDark ? Colors.white : WaveBookColors.ink,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: isDark ? Colors.white : WaveBookColors.ink,
        fontSize: 20,
        fontWeight: FontWeight.w800,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: WaveBookColors.pink,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: WaveBookColors.pink,
        side: const BorderSide(color: WaveBookColors.pink, width: 2),
        minimumSize: const Size.fromHeight(50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: isDark ? WaveBookColors.darkSurface : Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: isDark ? WaveBookColors.darkBorder : WaveBookColors.lightBorder),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: isDark ? WaveBookColors.darkBorder : WaveBookColors.lightBorder),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: WaveBookColors.pink, width: 2),
      ),
      labelStyle: TextStyle(color: isDark ? WaveBookColors.muted : WaveBookColors.rose),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: isDark ? WaveBookColors.darkSurface : Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: isDark ? WaveBookColors.darkBorder : WaveBookColors.lightBorder),
      ),
    ),
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      side: BorderSide(color: isDark ? WaveBookColors.darkBorder : WaveBookColors.lightBorder),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 64,
      backgroundColor: isDark ? WaveBookColors.darkSurface : Colors.white,
      indicatorColor: WaveBookColors.pink.withValues(alpha: 0.18),
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
      ),
    ),
    dividerColor: isDark ? WaveBookColors.darkBorder : WaveBookColors.lightBorder,
    textTheme: TextTheme(
      bodyMedium: TextStyle(color: isDark ? Colors.white : WaveBookColors.ink),
      bodySmall: TextStyle(color: isDark ? WaveBookColors.muted : const Color(0xFF6B6470)),
    ),
  );
}
