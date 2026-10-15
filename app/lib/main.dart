import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/auth/login_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/setup/business_setup_screen.dart';
import 'screens/splash_screen.dart';
import 'state/auth_state.dart';
import 'theme.dart';

void main() {
  runApp(const WaveBookApp());
}

class WaveBookApp extends StatelessWidget {
  const WaveBookApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AuthState(),
      child: MaterialApp(
        title: 'WaveBook',
        debugShowCheckedModeBanner: false,
        theme: buildWaveBookTheme(brightness: Brightness.light),
        darkTheme: buildWaveBookTheme(brightness: Brightness.dark),
        themeMode: ThemeMode.dark,
        home: const SplashScreen(),
      ),
    );
  }
}

class RootRouter extends StatelessWidget {
  const RootRouter({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    if (auth.loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!auth.isLoggedIn) {
      return const LoginScreen();
    }
    if (!auth.hasBusiness) {
      return const BusinessSetupScreen();
    }
    return const HomeScreen();
  }
}
