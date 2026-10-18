import 'package:flutter/material.dart';

import '../../services/app_update.dart';
import '../../services/notification_service.dart';
import 'tabs/availability_tab.dart';
import 'tabs/bookings_tab.dart';
import 'tabs/dashboard_tab.dart';
import 'tabs/more_tab.dart';
import 'tabs/services_tab.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;
  final NotificationService _notifications = NotificationService();

  static const _tabs = [
    DashboardTab(),
    BookingsTab(),
    ServicesTab(),
    AvailabilityTab(),
    MoreTab(),
  ];

  @override
  void initState() {
    super.initState();
    // Poll for new booking notifications and pop up when one arrives.
    _notifications.start(
      onNewBooking: (notification) {
        if (mounted) {
          showBookingNotificationPopup(context, notification);
        }
      },
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) checkForUpdate(context);
    });
  }

  @override
  void dispose() {
    _notifications.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Dashboard'),
          NavigationDestination(icon: Icon(Icons.event_outlined), selectedIcon: Icon(Icons.event), label: 'Bookings'),
          NavigationDestination(icon: Icon(Icons.content_cut_outlined), selectedIcon: Icon(Icons.content_cut), label: 'Services'),
          NavigationDestination(icon: Icon(Icons.schedule_outlined), selectedIcon: Icon(Icons.schedule), label: 'Availability'),
          NavigationDestination(icon: Icon(Icons.more_horiz), selectedIcon: Icon(Icons.more_horiz), label: 'More'),
        ],
      ),
    );
  }
}
