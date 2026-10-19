<?php
declare(strict_types=1);

const NOTIFY_TOKEN = 'h3r8aa01k6flmrbzzebtuc38pk0v40rb7wvmrzgczn1c0yw2';
const MAIL_FROM = 'notifications@neurowavesdatasystems.ng';
const MAIL_FROM_NAME = 'WaveBook';
const MAX_BODY_BYTES = 100000;

header('Content-Type: application/json; charset=utf-8');

function respond(int $code, array $data): void
{
    http_response_code($code);
    echo json_encode($data);
    exit;
}

function clean_header(string $value): string
{
    return trim(str_replace(["\r", "\n"], ' ', $value));
}

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    respond(200, ['status' => 'ok', 'service' => 'wavebook-notification']);
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    respond(405, ['status' => 'error', 'error' => 'method not allowed']);
}

$token = $_SERVER['HTTP_X_NOTIFY_TOKEN'] ?? '';
if (NOTIFY_TOKEN === 'REPLACE_WITH_NOTIFY_TOKEN' || !hash_equals(NOTIFY_TOKEN, $token)) {
    respond(401, ['status' => 'error', 'error' => 'unauthorized']);
}

$data = json_decode(file_get_contents('php://input') ?: '', true);
if (!is_array($data)) {
    respond(400, ['status' => 'error', 'error' => 'invalid json']);
}

$to = clean_header((string) ($data['to'] ?? ''));
$subject = clean_header((string) ($data['subject'] ?? ''));
$body = str_replace("\r\n", "\n", (string) ($data['body'] ?? ''));

if (!filter_var($to, FILTER_VALIDATE_EMAIL)) {
    respond(400, ['status' => 'error', 'error' => 'invalid recipient']);
}
if ($subject === '' || trim($body) === '') {
    respond(400, ['status' => 'error', 'error' => 'subject and body are required']);
}
if (strlen($body) > MAX_BODY_BYTES) {
    respond(400, ['status' => 'error', 'error' => 'body too large']);
}

$headers = [
    'From: ' . MAIL_FROM_NAME . ' <' . MAIL_FROM . '>',
    'Reply-To: ' . MAIL_FROM,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
    'X-Mailer: WaveBook-Notify',
];

$sent = mail(
    $to,
    '=?UTF-8?B?' . base64_encode($subject) . '?=',
    chunk_split(base64_encode($body)),
    implode("\r\n", $headers),
    '-f' . MAIL_FROM
);

if (!$sent) {
    respond(500, ['status' => 'error', 'error' => 'mail() failed on the hosting server']);
}

respond(200, ['status' => 'sent', 'to' => $to]);
