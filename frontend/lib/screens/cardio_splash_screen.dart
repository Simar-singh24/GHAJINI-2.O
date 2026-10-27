import 'package:flutter/material.dart';
import '../theme/cardio_theme.dart';
import 'cardio_home_screen.dart';

class CardioSplashScreen extends StatefulWidget {
  const CardioSplashScreen({super.key});

  @override
  State<CardioSplashScreen> createState() => _CardioSplashScreenState();
}

class _CardioSplashScreenState extends State<CardioSplashScreen> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CardioTheme.cardiacDeep,
      body: Container(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(0, -0.2),
            radius: 1.2,
            colors: [
              Color(0xFF991420),
              Color(0xFF3B0409),
              Color(0xFF150204),
            ],
          ),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 36),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            // Top Logo
            SafeArea(
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.favorite_border, color: Colors.white, size: 28),
                      const SizedBox(width: 8),
                      Text(
                        'CardioLife',
                        style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -0.5,
                            ),
                      ),
                    ],
                  ),
                  const Text(
                    'HEART & MEMORY CARE',
                    style: TextStyle(
                      color: Colors.white70,
                      fontSize: 10,
                      letterSpacing: 2.0,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),

            // Pulsing Heart Illustration Centerpiece
            ScaleTransition(
              scale: Tween<double>(begin: 0.94, end: 1.06).animate(
                CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Container(
                    width: 220,
                    height: 220,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFFDC2626).withValues(alpha: 0.4),
                          blurRadius: 50,
                          spreadRadius: 20,
                        ),
                      ],
                    ),
                  ),
                  const Icon(
                    Icons.favorite,
                    size: 160,
                    color: Color(0xFFDC2626),
                  ),
                ],
              ),
            ),

            // Bottom Hero Copy & Get Started
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                RichText(
                  text: const TextSpan(
                    style: TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.w800,
                      color: Colors.white,
                      height: 1.15,
                    ),
                    children: [
                      TextSpan(text: 'Your Heart\nDeserves the\n'),
                      TextSpan(
                        text: 'Best Care',
                        style: TextStyle(color: Color(0xFFFF6B7A)),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Advanced care for heart health & memory integrity. Early diagnosis. Provenance-backed truth.',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 24),

                // Button row
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white.withValues(alpha: 0.15),
                          foregroundColor: Colors.white,
                          elevation: 0,
                          shape: const StadiumBorder(
                            side: BorderSide(color: Colors.white30),
                          ),
                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
                        ),
                        onPressed: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const CardioHomeScreen()),
                          );
                        },
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'Get Started',
                              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                            ),
                            Icon(Icons.arrow_forward),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Container(
                      width: 58,
                      height: 58,
                      decoration: const BoxDecoration(
                        color: Colors.white,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.favorite, color: CardioTheme.primaryRed),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
