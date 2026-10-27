import 'package:flutter/material.dart';

class CardioTheme {
  // Crimson & Cardiac Palette from CardioLife Reference UI
  static const Color primaryRed = Color(0xFFA81825);
  static const Color primaryDarkRed = Color(0xFF7F111B);
  static const Color cardiacDeep = Color(0xFF1A070A);
  static const Color crimsonAccent = Color(0xFFB91C1C);
  static const Color crimsonLight = Color(0xFFFEE2E2);
  static const Color cardWhite = Color(0xFFFFFFFF);
  static const Color surfaceGray = Color(0xFFF9FAFB);
  static const Color textDark = Color(0xFF111827);
  static const Color textMuted = Color(0xFF6B7280);

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: surfaceGray,
      primaryColor: primaryRed,
      colorScheme: ColorScheme.fromSeed(
        seedColor: primaryRed,
        primary: primaryRed,
        secondary: primaryDarkRed,
        surface: cardWhite,
      ),
      fontFamily: 'Outfit',
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: IconThemeData(color: textDark),
        titleTextStyle: TextStyle(
          color: textDark,
          fontSize: 18,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}
