<?php
$cfg = include('/config/www/freshrss/data/users/admin/config.php');
echo 'hash: ' . $cfg['apiPasswordHash'] . PHP_EOL;
echo 'verify: ' . (password_verify('rigdev2024', $cfg['apiPasswordHash']) ? 'MATCH' : 'NO MATCH') . PHP_EOL;
