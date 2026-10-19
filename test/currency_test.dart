import 'package:flutter_test/flutter_test.dart';
import 'package:wavebook_app/theme.dart';

void main() {
  group('currencySymbol', () {
    test('maps supported currencies to their symbols', () {
      expect(currencySymbol('GBP'), '£');
      expect(currencySymbol('USD'), r'$');
      expect(currencySymbol('CAD'), r'C$');
      expect(currencySymbol('EUR'), '€');
      expect(currencySymbol('AUD'), r'A$');
      expect(currencySymbol('NZD'), r'NZ$');
      expect(currencySymbol('NGN'), '₦');
      expect(currencySymbol('KES'), 'KSh');
      expect(currencySymbol('ZAR'), 'R');
    });

    test('defaults to GBP for missing or unknown codes', () {
      expect(currencySymbol(''), '£');
      expect(currencySymbol('jpy'), '£');
    });
  });
}
