import 'package:flutter_test/flutter_test.dart';
import 'package:gmail_dashboard/main.dart';

void main() {
  testWidgets('App renders without crashing', (WidgetTester tester) async {
    await tester.pumpWidget(const GmailAgentApp());
    expect(find.byType(GmailAgentApp), findsOneWidget);
  });
}
