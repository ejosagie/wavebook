import 'dart:async';

import 'package:flutter/material.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class ChatsScreen extends StatefulWidget {
  const ChatsScreen({super.key});

  @override
  State<ChatsScreen> createState() => _ChatsScreenState();
}

class _ChatsScreenState extends State<ChatsScreen> {
  final _api = ApiClient();
  List<Chat> _chats = [];
  bool _loading = true;
  String? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 15), (_) => _load(silent: true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    try {
      final data = await _api.get('/api/chats');
      if (!mounted) return;
      setState(() {
        _chats = (data as List).map((c) => Chat.fromJson(c as Map<String, dynamic>)).toList();
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted && !silent) setState(() => _error = e.message);
    } finally {
      if (mounted && !silent) setState(() => _loading = false);
    }
  }

  Future<void> _openChat(Chat chat) async {
    await Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => ChatThreadScreen(chat: chat)));
    _load(silent: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Customer Chats')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          Icon(Icons.cloud_off, size: 48, color: WaveBookColors.muted),
          const SizedBox(height: 12),
          Text(_error!, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Center(child: ElevatedButton(onPressed: _load, child: const Text('Retry'))),
        ],
      );
    }
    if (_chats.isEmpty) {
      return ListView(
        children: const [
          SizedBox(height: 100),
          Icon(Icons.chat_bubble_outline, size: 56, color: WaveBookColors.muted),
          SizedBox(height: 12),
          Text(
            'No chats yet',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
          SizedBox(height: 6),
          Text(
            'When customers start a chat from your booking website, '
            'their conversations will appear here.',
            textAlign: TextAlign.center,
            style: TextStyle(color: WaveBookColors.muted),
          ),
        ],
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        itemCount: _chats.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (context, i) {
          final chat = _chats[i];
          final isCustomerLast = chat.lastSender == 'customer';
          return ListTile(
            leading: CircleAvatar(
              backgroundColor: WaveBookColors.pink.withValues(alpha: 0.12),
              child: Text(
                chat.customerName.isNotEmpty ? chat.customerName[0].toUpperCase() : '?',
                style: const TextStyle(color: WaveBookColors.pink, fontWeight: FontWeight.w700),
              ),
            ),
            title: Text(
              chat.customerName,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            subtitle: Text(
              chat.lastMessage.isEmpty
                  ? 'No messages yet'
                  : '${isCustomerLast ? '' : 'You: '}${chat.lastMessage}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            trailing: chat.unread > 0
                ? Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(
                      color: WaveBookColors.pink,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '${chat.unread}',
                      style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w800),
                    ),
                  )
                : null,
            onTap: () => _openChat(chat),
          );
        },
      ),
    );
  }
}

class ChatThreadScreen extends StatefulWidget {
  final Chat chat;

  const ChatThreadScreen({super.key, required this.chat});

  @override
  State<ChatThreadScreen> createState() => _ChatThreadScreenState();
}

class _ChatThreadScreenState extends State<ChatThreadScreen> {
  final _api = ApiClient();
  final _controller = TextEditingController();
  final _scroll = ScrollController();
  List<ChatMessage> _messages = [];
  bool _loading = true;
  String? _error;
  Timer? _timer;
  int _lastId = 0;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _poll());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await _api.get('/api/chats/${widget.chat.id}/messages');
      if (!mounted) return;
      setState(() {
        _messages = ((data as Map<String, dynamic>)['messages'] as List)
            .map((m) => ChatMessage.fromJson(m as Map<String, dynamic>))
            .toList();
        _error = null;
      });
      _lastId = _messages.isEmpty ? 0 : _messages.last.id;
      _scrollToBottom();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _poll() async {
    try {
      final data = await _api.get('/api/chats/${widget.chat.id}/messages?since=$_lastId');
      final fresh = ((data as Map<String, dynamic>)['messages'] as List)
          .map((m) => ChatMessage.fromJson(m as Map<String, dynamic>))
          .toList();
      if (fresh.isEmpty || !mounted) return;
      setState(() => _messages = [..._messages, ...fresh]);
      _lastId = fresh.last.id;
      _scrollToBottom();
    } catch (_) {
      // Silent: polling failures shouldn't disturb the user.
    }
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    _controller.clear();
    try {
      final m = await _api.post('/api/chats/${widget.chat.id}/messages', body: {'body': text});
      if (!mounted) return;
      setState(() {
        _messages = [..._messages, ChatMessage.fromJson(m as Map<String, dynamic>)];
      });
      _lastId = _messages.last.id;
      _scrollToBottom();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.chat.customerName)),
      body: Column(
        children: [
          Expanded(child: _buildMessages()),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      decoration: InputDecoration(
                        hintText: 'Reply to ${widget.chat.customerName}...',
                        filled: true,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(24),
                          borderSide: BorderSide.none,
                        ),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                      ),
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    icon: const Icon(Icons.send),
                    color: Colors.white,
                    onPressed: _send,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMessages() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }
    if (_messages.isEmpty) {
      return const Center(
        child: Text('No messages yet. Say hello!', style: TextStyle(color: WaveBookColors.muted)),
      );
    }
    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.all(12),
      itemCount: _messages.length,
      itemBuilder: (context, i) {
        final m = _messages[i];
        final isOwner = m.sender == 'owner';
        return Align(
          alignment: isOwner ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
            decoration: BoxDecoration(
              color: isOwner ? WaveBookColors.pink : Theme.of(context).colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(16),
                topRight: const Radius.circular(16),
                bottomLeft: Radius.circular(isOwner ? 16 : 4),
                bottomRight: Radius.circular(isOwner ? 4 : 16),
              ),
            ),
            child: Text(
              m.body,
              style: TextStyle(color: isOwner ? Colors.white : null, fontSize: 15),
            ),
          ),
        );
      },
    );
  }
}
