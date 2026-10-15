import 'package:flutter_test/flutter_test.dart';

import 'package:wavebook_app/main.dart';

void main() {
  testWidgets('WaveBook app builds', (WidgetTester tester) async {
    await tester.pumpWidget(const WaveBookApp());
    expect(find.byType(WaveBookApp), findsOneWidget);
  });
}
