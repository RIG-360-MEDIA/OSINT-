<?php
echo "DATA_PATH env: " . (getenv('DATA_PATH') ?: 'NOT SET') . "\n";
echo "CLISERVER: " . PHP_SAPI . "\n";

// Try to find where FreshRSS looks for data
$possiblePaths = [
    getenv('DATA_PATH'),
    '/config/www/freshrss/data',
    '/app/www/data',
    '/data',
];
foreach ($possiblePaths as $p) {
    if ($p && is_dir($p)) {
        echo "Dir exists: $p\n";
        $cfg = $p . '/users/admin/config.php';
        if (file_exists($cfg)) {
            $data = include($cfg);
            $hash = $data['apiPasswordHash'] ?? 'NOT SET';
            echo "  apiPasswordHash: $hash\n";
            echo "  verify rigdev2024: " . (password_verify('rigdev2024', $hash) ? 'MATCH' : 'NO MATCH') . "\n";
        } else {
            echo "  No admin config at $cfg\n";
        }
    }
}
