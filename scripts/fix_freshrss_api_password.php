<?php
$password = 'rigdev2024';
$hash = password_hash($password, PASSWORD_BCRYPT);

$file = '/config/www/freshrss/data/users/admin/config.php';
$content = file_get_contents($file);

// Use preg_replace_callback to avoid back-reference interpretation of $2y in hash
$content = preg_replace_callback(
    "/'apiPasswordHash' => '[^']*'/",
    function() use ($hash) {
        return "'apiPasswordHash' => '" . $hash . "'";
    },
    $content
);

file_put_contents($file, $content);

// Verify
$cfg = include($file);
echo (password_verify($password, $cfg['apiPasswordHash']) ? "Hash verified OK\n" : "Hash BROKEN\n");
echo "Stored hash: " . $cfg['apiPasswordHash'] . "\n";
