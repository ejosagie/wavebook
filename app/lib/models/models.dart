class User {
  final int id;
  final String email;
  final String fullName;
  final String phone;
  final String role;
  final int? businessId;

  User({
    required this.id,
    required this.email,
    required this.fullName,
    required this.phone,
    required this.role,
    this.businessId,
  });

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as int,
        email: json['email'] as String? ?? '',
        fullName: json['full_name'] as String? ?? '',
        phone: json['phone'] as String? ?? '',
        role: json['role'] as String? ?? 'owner',
        businessId: json['business_id'] as int?,
      );
}

class Business {
  final int id;
  final String slug;
  final String name;
  final String tagline;
  final String aboutText;
  final String aboutImage;
  final String logoPath;
  final String rules;
  final String contactPhone;
  final String contactEmail;
  final String address;
  final String instagram;
  final String facebook;
  final String tiktok;
  final String openingHours;
  final double depositAmount;
  final int bufferMinutes;
  final String currency;
  final String subscriptionStatus;

  Business({
    required this.id,
    required this.slug,
    required this.name,
    required this.tagline,
    required this.aboutText,
    required this.aboutImage,
    required this.logoPath,
    required this.rules,
    required this.contactPhone,
    required this.contactEmail,
    required this.address,
    required this.instagram,
    required this.facebook,
    required this.tiktok,
    required this.openingHours,
    required this.depositAmount,
    required this.bufferMinutes,
    required this.currency,
    required this.subscriptionStatus,
  });

  factory Business.fromJson(Map<String, dynamic> json) => Business(
        id: json['id'] as int,
        slug: json['slug'] as String? ?? '',
        name: json['name'] as String? ?? '',
        tagline: json['tagline'] as String? ?? '',
        aboutText: json['about_text'] as String? ?? '',
        aboutImage: json['about_image'] as String? ?? '',
        logoPath: json['logo_path'] as String? ?? '',
        rules: json['rules'] as String? ?? '',
        contactPhone: json['contact_phone'] as String? ?? '',
        contactEmail: json['contact_email'] as String? ?? '',
        address: json['address'] as String? ?? '',
        instagram: json['instagram'] as String? ?? '',
        facebook: json['facebook'] as String? ?? '',
        tiktok: json['tiktok'] as String? ?? '',
        openingHours: json['opening_hours'] as String? ?? '',
        depositAmount: (json['deposit_amount'] as num?)?.toDouble() ?? 20.0,
        bufferMinutes: json['buffer_minutes'] as int? ?? 30,
        currency: json['currency'] as String? ?? 'GBP',
        subscriptionStatus: json['subscription_status'] as String? ?? 'trial',
      );

  Map<String, dynamic> toJson() => {
        'name': name,
        'tagline': tagline,
        'about_text': aboutText,
        'rules': rules,
        'contact_phone': contactPhone,
        'contact_email': contactEmail,
        'address': address,
        'instagram': instagram,
        'facebook': facebook,
        'tiktok': tiktok,
        'opening_hours': openingHours,
        'deposit_amount': depositAmount,
        'buffer_minutes': bufferMinutes,
      };
}

class Service {
  final int id;
  final String name;
  final String description;
  final double price;
  final int durationMinutes;
  final int sortOrder;

  Service({
    required this.id,
    required this.name,
    required this.description,
    required this.price,
    required this.durationMinutes,
    required this.sortOrder,
  });

  factory Service.fromJson(Map<String, dynamic> json) => Service(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        description: json['description'] as String? ?? '',
        price: (json['price'] as num?)?.toDouble() ?? 0,
        durationMinutes: json['duration_minutes'] as int? ?? 60,
        sortOrder: json['sort_order'] as int? ?? 0,
      );

  Map<String, dynamic> toJson() => {
        'name': name,
        'description': description,
        'price': price,
        'duration_minutes': durationMinutes,
      };
}

class Booking {
  final int id;
  final String customerName;
  final String customerEmail;
  final String customerPhone;
  final int? serviceId;
  final String serviceName;
  final double servicePrice;
  final int serviceDurationMinutes;
  final String date;
  final String time;
  final String notes;
  final String status;
  final String confirmationFile;
  final String createdAt;

  Booking({
    required this.id,
    required this.customerName,
    required this.customerEmail,
    required this.customerPhone,
    this.serviceId,
    required this.serviceName,
    required this.servicePrice,
    required this.serviceDurationMinutes,
    required this.date,
    required this.time,
    required this.notes,
    required this.status,
    required this.confirmationFile,
    required this.createdAt,
  });

  factory Booking.fromJson(Map<String, dynamic> json) => Booking(
        id: json['id'] as int,
        customerName: json['customer_name'] as String? ?? '',
        customerEmail: json['customer_email'] as String? ?? '',
        customerPhone: json['customer_phone'] as String? ?? '',
        serviceId: json['service_id'] as int?,
        serviceName: json['service_name'] as String? ?? '',
        servicePrice: (json['service_price'] as num?)?.toDouble() ?? 0,
        serviceDurationMinutes: json['service_duration_minutes'] as int? ?? 60,
        date: json['date'] as String? ?? '',
        time: json['time'] as String? ?? '',
        notes: json['notes'] as String? ?? '',
        status: json['status'] as String? ?? 'pending',
        confirmationFile: json['confirmation_file'] as String? ?? '',
        createdAt: json['created_at'] as String? ?? '',
      );
}

class DayConfig {
  final bool enabled;
  final String start;
  final String end;

  DayConfig({required this.enabled, required this.start, required this.end});

  factory DayConfig.fromJson(Map<String, dynamic> json) => DayConfig(
        enabled: json['enabled'] as bool? ?? true,
        start: json['start'] as String? ?? '09:00',
        end: json['end'] as String? ?? '17:00',
      );

  Map<String, dynamic> toJson() => {'enabled': enabled, 'start': start, 'end': end};
}

class Availability {
  final Map<String, DayConfig> workingDays;
  final List<String> blockedDates;
  final Map<String, List<String>> blockedSlots;
  int slotInterval;

  Availability({
    required this.workingDays,
    required this.blockedDates,
    required this.blockedSlots,
    required this.slotInterval,
  });

  factory Availability.fromJson(Map<String, dynamic> json) {
    final days = <String, DayConfig>{};
    (json['working_days'] as Map<String, dynamic>? ?? {}).forEach((k, v) {
      days[k] = DayConfig.fromJson(v as Map<String, dynamic>);
    });
    return Availability(
      workingDays: days,
      blockedDates: (json['blocked_dates'] as List? ?? []).cast<String>(),
      blockedSlots: (json['blocked_slots'] as Map<String, dynamic>? ?? {})
          .map((k, v) => MapEntry(k, (v as List).cast<String>())),
      slotInterval: json['slot_interval'] as int? ?? 30,
    );
  }

  Map<String, dynamic> toJson() => {
        'working_days': workingDays.map((k, v) => MapEntry(k, v.toJson())),
        'blocked_dates': blockedDates,
        'blocked_slots': blockedSlots,
        'slot_interval': slotInterval,
      };
}

class StaffMember {
  final int id;
  final int? userId;
  final String email;
  final String fullName;
  final String phone;
  final bool active;

  StaffMember({
    required this.id,
    this.userId,
    required this.email,
    required this.fullName,
    required this.phone,
    required this.active,
  });

  factory StaffMember.fromJson(Map<String, dynamic> json) => StaffMember(
        id: json['id'] as int,
        userId: json['user_id'] as int?,
        email: json['email'] as String? ?? '',
        fullName: json['full_name'] as String? ?? '',
        phone: json['phone'] as String? ?? '',
        active: (json['active'] as int? ?? 1) == 1,
      );
}

class Customer {
  final int id;
  final String name;
  final String email;
  final String phone;
  final String notes;
  final int bookingCount;

  Customer({
    required this.id,
    required this.name,
    required this.email,
    required this.phone,
    required this.notes,
    required this.bookingCount,
  });

  factory Customer.fromJson(Map<String, dynamic> json) => Customer(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        email: json['email'] as String? ?? '',
        phone: json['phone'] as String? ?? '',
        notes: json['notes'] as String? ?? '',
        bookingCount: json['booking_count'] as int? ?? 0,
      );
}

class GalleryItem {
  final int slot;
  final String path;
  final String caption;

  GalleryItem({required this.slot, required this.path, required this.caption});

  factory GalleryItem.fromJson(Map<String, dynamic> json) => GalleryItem(
        slot: json['slot'] as int,
        path: json['path'] as String? ?? '',
        caption: json['caption'] as String? ?? '',
      );
}

class SubscriptionInfo {
  final String status;
  final double priceGbp;
  final int maxStaff;

  SubscriptionInfo({
    required this.status,
    required this.priceGbp,
    required this.maxStaff,
  });

  factory SubscriptionInfo.fromJson(Map<String, dynamic> json) => SubscriptionInfo(
        status: json['status'] as String? ?? 'trial',
        priceGbp: (json['price_gbp'] as num?)?.toDouble() ?? 9.99,
        maxStaff: json['max_staff'] as int? ?? 5,
      );
}
