<?php
declare(strict_types=1);

/**
 * commute-plan web dashboard
 * --------------------------
 * Tabs:
 *  - Planner: run CLI (test/evening/morning) and show output
 *  - Config (GUI): structured form over commute_config.toml
 *  - Config (raw): plain-text TOML editor
 *  - Feedback: comfort logging + history + exports + suggest
 */

session_start();

$baseDir     = realpath(__DIR__ . '/..') ?: (__DIR__ . '/..');
$configPath  = $baseDir . '/secrets/commute_config.toml';
$examplePath = $baseDir . '/config/commute_config.example.toml';
$pythonBin   = $baseDir . '/venv/bin/python';

// ---------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------
function h(?string $s): string {
    return htmlspecialchars((string)($s ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function wore_level_label($lvl): string {
    if ($lvl === null || $lvl === '') return '';
    $n = (int)$lvl;
    if (!in_array($n, [1,2,3,4,5], true)) return '';
    return match ($n) {
        1 => "Level 1 (short sleeve)",
        2 => "Level 2 (long sleeve)",
        3 => "Level 3 (long sleeve + undershirt)",
        4 => "Level 4 (+ coat/jacket)",
        5 => "Level 5 (coat + gloves/hat/scarf)",
    };
}

function comfort_emoji(string $raw): string {
    $v = strtolower(trim($raw));
    return match ($v) {
        'too_cold' => "🥶",
        'a_bit_cold', 'a-little-cold', 'abitcold' => "😬",
        'comfortable', 'ok', 'good' => "🙂",
        'a_bit_hot', 'a-little-hot', 'abithot' => "😅",
        'too_hot' => "🥵",
        default => "",
    };
}

// Map outerwear string -> emoji (mirror of Python weekly_pretty)
function commute_outerwear_emoji(?string $outerwear): string {
    if ($outerwear === null || $outerwear === '') return "👕";
    $o = strtolower($outerwear);

    if (str_contains($o, 'heavy') || str_contains($o, 'coat')) return "🧥";
    if (str_contains($o, 'jacket')) return "🧶";
    if (str_contains($o, 'long')) return "👕";
    if (str_contains($o, 'shorts')) return "🩳👕";
    if (str_contains($o, 'tshirt') || str_contains($o, 't-shirt') || str_contains($o, 'short_sleeve')) return "👕";

    return "👕";
}

// Map walk_score string -> emoji
function commute_walk_emoji(?string $score): string {
    if ($score === null || $score === '') return "⚠️";
    $s = strtolower($score);

    if (in_array($s, ['ok', 'good', 'great', 'yes'], true)) return "✅";
    if (in_array($s, ['maybe', 'borderline', 'mixed', 'caution'], true)) return "⚠️";
    if (in_array($s, ['avoid', 'bad', 'no'], true)) return "🚫";

    return "⚠️";
}

// ---------------------------------------------------------------------
// CSRF
// ---------------------------------------------------------------------
if (empty($_SESSION['csrf_token'])) {
    $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
}
$csrfToken = $_SESSION['csrf_token'];

// ---------------------------------------------------------------------
// Comfort DB helpers (SQLite3, consistent everywhere)
// ---------------------------------------------------------------------
function comfort_db_path(string $baseDir): string {
    $env = trim((string)getenv('COMFORT_DB'));
    if ($env !== '') return $env;
    return $baseDir . '/data/comfort.db';
}

function comfort_sqlite_open_ro(string $dbPath): SQLite3 {
    $db = new SQLite3($dbPath, SQLITE3_OPEN_READONLY);
    $db->busyTimeout(2000);
    return $db;
}

function comfort_sqlite_open_rw(string $dbPath): SQLite3 {
    $db = new SQLite3($dbPath, SQLITE3_OPEN_READWRITE);
    $db->busyTimeout(2000);
    return $db;
}

function comfort_read_recent(string $dbPath, int $limit = 25): array {
    if (!class_exists('SQLite3')) {
        return [['__error' => 'PHP SQLite3 extension not available (class SQLite3 missing).']];
    }
    if (!is_file($dbPath)) {
        return [['__error' => 'comfort.db not found at: ' . $dbPath]];
    }

    $rows = [];
    $db = comfort_sqlite_open_ro($dbPath);
    try {
        $stmt = $db->prepare('
          SELECT id, timestamp_local, source, context, leg, location, activity, wore, wore_level, comfort,
                 temp_f, feels_like_f, wind_speed_mph, wind_gust_mph, humidity_pct, pop_pct
          FROM comfort_logs
          ORDER BY id DESC
          LIMIT :lim
        ');
        $stmt->bindValue(':lim', $limit, SQLITE3_INTEGER);
        $res = $stmt->execute();
        while ($res && ($r = $res->fetchArray(SQLITE3_ASSOC))) {
            $rows[] = $r;
        }
    } finally {
        $db->close();
    }
    return $rows;
}

function comfort_run_python(array $args, string $baseDir, string $pythonBin): array {
    $cmd = 'cd ' . escapeshellarg($baseDir) . ' && ' . escapeshellarg($pythonBin) . ' -m app.src.comfort_cli';
    foreach ($args as $a) {
        $cmd .= ' ' . escapeshellarg((string)$a);
    }
    $out = [];
    $rc  = 0;
    exec($cmd . ' 2>&1', $out, $rc);
    return [$rc, implode("\n", $out)];
}

function comfort_run_suggest(string $baseDir, string $pythonBin): array {
    $cmd = escapeshellarg($pythonBin) . ' -m app.src.comfort_suggest';
    $des = [
        0 => ['pipe','r'],
        1 => ['pipe','w'],
        2 => ['pipe','w'],
    ];
    $proc = @proc_open($cmd, $des, $pipes, $baseDir);
    if (!is_resource($proc)) {
        return [1, "Failed to start comfort_suggest process."];
    }

    @fclose($pipes[0]);
    $out = stream_get_contents($pipes[1]); @fclose($pipes[1]);
    $err = stream_get_contents($pipes[2]); @fclose($pipes[2]);
    $code = proc_close($proc);

    $txt = trim((string)$out . ($err ? ("\n" . $err) : ''));
    if ($txt === '') $txt = "(no output)";
    if ($code !== 0) $txt = "[exit=$code]\n" . $txt;

    return [$code, $txt];
}

// ---------------------------------------------------------------------
// Config schema: sections, keys, defaults, comments, validation hints
// ---------------------------------------------------------------------
$CONFIG_SCHEMA = [
    'morning' => [
        'departure' => [
            'type'    => 'time',
            'label'   => 'Morning departure',
            'default' => '07:00',
            'comment' => 'nominal leave time (HH:MM)',
        ],
        'flex_minutes' => [
            'type'    => 'int',
            'label'   => 'Morning flex minutes',
            'default' => 30,
            'min'     => 0,
            'max'     => 180,
            'comment' => '+/- minutes we can shift to dodge rain',
        ],
    ],
    'afternoon' => [
        'departure' => [
            'type'    => 'time',
            'label'   => 'Afternoon departure',
            'default' => '15:30',
            'comment' => 'nominal leave time (HH:MM)',
        ],
        'flex_minutes' => [
            'type'    => 'int',
            'label'   => 'Afternoon flex minutes',
            'default' => 30,
            'min'     => 0,
            'max'     => 180,
            'comment' => '+/- minutes we can shift to dodge rain',
        ],
    ],
    'temperature_f' => [
        'cold_coat_below' => [
            'type'    => 'int',
            'label'   => 'Cold coat below (°F)',
            'default' => 35,
            'min'     => -20,
            'max'     => 80,
            'comment' => '<= this: heavy coat',
        ],
        'light_jacket_below' => [
            'type'    => 'int',
            'label'   => 'Light jacket below (°F)',
            'default' => 55,
            'min'     => -20,
            'max'     => 90,
            'comment' => '<= this: light jacket/hoodie',
        ],
        'short_sleeves_above' => [
            'type'    => 'int',
            'label'   => 'Short sleeves above (°F)',
            'default' => 70,
            'min'     => -20,
            'max'     => 110,
            'comment' => '>= this: t-shirt fine',
        ],
        'shorts_above' => [
            'type'    => 'int',
            'label'   => 'Shorts above (°F)',
            'default' => 80,
            'min'     => -20,
            'max'     => 120,
            'comment' => '>= this: shorts recommended',
        ],
    ],
    'rain' => [
        'umbrella_pop_threshold' => [
            'type'    => 'int',
            'label'   => 'Umbrella POP threshold (%)',
            'default' => 30,
            'min'     => 0,
            'max'     => 100,
            'comment' => '% chance where umbrella recommended',
        ],
        'avoid_walk_pop_threshold' => [
            'type'    => 'int',
            'label'   => 'Avoid-walk POP threshold (%)',
            'default' => 70,
            'min'     => 0,
            'max'     => 100,
            'comment' => '% chance where walking is discouraged',
        ],
    ],
    'wind' => [
        'max_walkable_speed_mph' => [
            'type'    => 'int',
            'label'   => 'Max walkable sustained wind (mph)',
            'default' => 25,
            'min'     => 0,
            'max'     => 60,
            'comment' => 'Above this, walking is considered unsafe/unpleasant.',
        ],
        'max_walkable_gust_mph' => [
            'type'    => 'int',
            'label'   => 'Max walkable gusts (mph)',
            'default' => 40,
            'min'     => 0,
            'max'     => 80,
            'comment' => 'Above this, walking is considered unsafe/unpleasant.',
        ],
    ],
    'minutely' => [
        'enable_morning_refinement' => [
            'type'    => 'bool',
            'label'   => 'Enable morning minutely refinement',
            'default' => true,
            'comment' => 'Use OpenWeather minutely data in morning runs.',
        ],
        'window_minutes' => [
            'type'    => 'int',
            'label'   => 'Refinement window (± minutes)',
            'default' => 20,
            'min'     => 0,
            'max'     => 120,
            'comment' => '+/- this many minutes around nominal departure',
        ],
    ],
    'change_thresholds' => [
        'temp_change_significant' => [
            'type'    => 'int',
            'label'   => 'Temperature change significant (°F)',
            'default' => 5,
            'min'     => 0,
            'max'     => 50,
            'comment' => '°F change that triggers a meaningful update',
        ],
        'pop_change_significant' => [
            'type'    => 'int',
            'label'   => 'POP change significant (points)',
            'default' => 20,
            'min'     => 0,
            'max'     => 100,
            'comment' => 'POP percentage points change (0-100 scale)',
        ],
        'wind_speed_change_significant' => [
            'type'    => 'int',
            'label'   => 'Wind speed change significant (mph)',
            'default' => 8,
            'min'     => 0,
            'max'     => 60,
            'comment' => 'mph change in sustained wind',
        ],
        'wind_gust_change_significant' => [
            'type'    => 'int',
            'label'   => 'Wind gust change significant (mph)',
            'default' => 12,
            'min'     => 0,
            'max'     => 80,
            'comment' => 'mph change in gusts',
        ],
        'clothing_change_triggers_update' => [
            'type'    => 'bool',
            'label'   => 'Clothing change triggers update',
            'default' => true,
            'comment' => 'If clothing recommendation changes, treat as meaningful.',
        ],
    ],
    'alerts' => [
        'weather_fail_streak_threshold' => [
            'type'    => 'int',
            'label'   => 'Weather failure streak threshold',
            'default' => 3,
            'min'     => 1,
            'max'     => 50,
            'comment' => 'If weather_update fails this many times in a row, send a DM.',
        ],
        'weather_fail_cooldown_minutes' => [
            'type'    => 'int',
            'label'   => 'Weather failure DM cooldown (minutes)',
            'default' => 60,
            'min'     => 1,
            'max'     => 1440,
            'comment' => 'After sending a failure DM, wait at least this long before another.',
        ],
    ],
];

// ---------------------------------------------------------------------
// Helpers: load config text, parse into values, build TOML from values
// ---------------------------------------------------------------------
function load_config_text(string $configPath, string $examplePath): array {
    $msg = '';
    $err = '';

    if (is_readable($configPath)) {
        $text = file_get_contents($configPath) ?: '';
    } elseif (is_readable($examplePath)) {
        $text = "# Using example config as a starting point.\n" . (file_get_contents($examplePath) ?: '');
        $msg  = 'No secrets/commute_config.toml found; showing example config.';
    } else {
        $text = "# No config files found.\n"
              . "# Expected: secrets/commute_config.toml or config/commute_config.example.toml\n";
        $err  = 'No config files found. Create config/commute_config.example.toml and/or secrets/commute_config.toml.';
    }

    return [$text, $msg, $err];
}

function parse_toml_to_values(string $toml, array $schema): array {
    $values = [];
    $lines = preg_split('/\R/', $toml);
    $section = null;

    foreach ($lines as $rawLine) {
        $line = trim($rawLine);
        if ($line === '' || str_starts_with($line, '#')) continue;

        if ($line[0] === '[' && substr($line, -1) === ']') {
            $sectionName = trim(substr($line, 1, -1));
            $section = $sectionName;
            continue;
        }
        if (!$section || !isset($schema[$section])) continue;
        if (!str_contains($line, '=')) continue;

        [$key, $rest] = array_map('trim', explode('=', $line, 2));
        if (!isset($schema[$section][$key])) continue;

        $rest = preg_replace('/\s+#.*$/', '', $rest);
        $rest = trim((string)$rest);

        $type = $schema[$section][$key]['type'] ?? 'string';
        if ($type === 'bool') {
            $values[$section][$key] = (strtolower($rest) === 'true');
        } elseif ($type === 'int') {
            $values[$section][$key] = (int)$rest;
        } else { // time/string
            $values[$section][$key] = trim($rest, '"');
        }
    }

    foreach ($schema as $sectionName => $keys) {
        foreach ($keys as $key => $meta) {
            if (!isset($values[$sectionName][$key])) {
                $values[$sectionName][$key] = $meta['default'] ?? null;
            }
        }
    }

    return $values;
}

function build_toml_from_values(array $schema, array $values): string {
    $lines = [];
    $lines[] = '# Commute planner thresholds & windows';
    $lines[] = '# Copy this file to secrets/commute_config.toml and edit there for real use.';
    $lines[] = '';

    foreach ($schema as $sectionName => $keys) {
        $lines[] = '[' . $sectionName . ']';
        foreach ($keys as $key => $meta) {
            $type    = $meta['type'] ?? 'string';
            $comment = $meta['comment'] ?? '';
            $val     = $values[$sectionName][$key] ?? ($meta['default'] ?? null);

            if ($type === 'bool') {
                $valStr = $val ? 'true' : 'false';
            } elseif ($type === 'int') {
                $valStr = (string)(int)$val;
            } else {
                $valStr = '"' . (string)$val . '"';
            }

            if ($comment !== '') {
                $lines[] = sprintf('%s = %s       # %s', $key, $valStr, $comment);
            } else {
                $lines[] = sprintf('%s = %s', $key, $valStr);
            }
        }
        $lines[] = '';
    }

    return implode("\n", $lines) . "\n";
}

// ---------------------------------------------------------------------
// Initial load
// ---------------------------------------------------------------------
[$configText, $configMessage, $configError] = load_config_text($configPath, $examplePath);
$values = parse_toml_to_values($configText, $CONFIG_SCHEMA);

// ---------------------------------------------------------------------
// UI state + messages
// ---------------------------------------------------------------------
$activeTab = (string)($_POST['tab'] ?? ($_GET['tab'] ?? 'planner'));

$plannerMode   = '';
$plannerOutput = '';
$plannerError  = '';

$weeklyOverview      = null;
$weeklyOverviewError = '';

$configGuiMessages = [];
$configGuiErrors   = [];
$configGuiValues   = $values;

$rawConfigText    = $configText;
$rawConfigMessage = $configMessage;
$rawConfigError   = $configError;

// Feedback / comfort UI state
$comfortMessages = [];
$comfortErrors   = [];
$comfortOutput   = '';
$comfortSuggestOutput = null;

// Default comfort form values
$comfortForm = [
    'timestamp_local' => 'now',
    'context'         => 'commute',
    'leg'             => '',
    'activity'        => '',
    'comfort'         => '',
    'wore'            => '',
    'wore_level'      => '',
    'location'        => '',
    'dry_run'         => false,
];

// Keep comfort form sticky on POST
function comfort_form_from_post(array &$comfortForm): void {
    foreach (array_keys($comfortForm) as $k) {
        if ($k === 'dry_run') continue;
        if (isset($_POST[$k])) $comfortForm[$k] = (string)$_POST[$k];
    }
    $comfortForm['dry_run'] = !empty($_POST['dry_run']);
}

// ---------------------------------------------------------------------
// Comfort History (GET) — runs regardless of tab, but shown in Feedback
// ---------------------------------------------------------------------
$historyFrom  = trim((string)($_GET['history_from'] ?? ''));
$historyTo    = trim((string)($_GET['history_to'] ?? ''));
$historyLimit = (int)($_GET['history_limit'] ?? 200);

$historyContext   = trim((string)($_GET['history_context'] ?? ''));
$historyLeg       = trim((string)($_GET['history_leg'] ?? ''));
$historyComfort   = trim((string)($_GET['history_comfort'] ?? ''));
$historyWoreLevel = trim((string)($_GET['history_wore_level'] ?? ''));

$historyWoreLevelI = null;
if ($historyWoreLevel !== '') {
    $tmp = (int)$historyWoreLevel;
    if (in_array($tmp, [1,2,3,4,5], true)) $historyWoreLevelI = $tmp;
}

if ($historyLimit < 10) $historyLimit = 10;
if ($historyLimit > 2000) $historyLimit = 2000;

$reDate = '/^\d{4}-\d{2}-\d{2}$/';
$fromIso = '';
$toIso   = '';
if ($historyFrom !== '' && preg_match($reDate, $historyFrom)) $fromIso = $historyFrom . 'T00:00:00';
if ($historyTo   !== '' && preg_match($reDate, $historyTo))   $toIso   = $historyTo   . 'T23:59:59';

$historyRows = [];
$historyErr  = '';
$bandRows    = [];

$dbPathComfort = comfort_db_path($baseDir);

// If any history filters are present, default tab to feedback
if ($activeTab === 'planner') {
    $historyKeys = ['history_from','history_to','history_limit','history_context','history_leg','history_comfort','history_wore_level','history_export'];
    foreach ($historyKeys as $k) {
        if (isset($_GET[$k]) && (string)$_GET[$k] !== '') {
            $activeTab = 'feedback';
            break;
        }
    }
}

// ---------------------------------------------------------------------
// Handle POST actions (single router)
// ---------------------------------------------------------------------
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $token = (string)($_POST['csrf_token'] ?? '');
    if (!hash_equals($csrfToken, $token)) {
        http_response_code(400);
        die('Invalid CSRF token.');
    }

    $action = (string)($_POST['action'] ?? '');

    // --- Planner ------------------------------------------------------
    if ($action === 'run_plan') {
        $activeTab = 'planner';
        $mode      = (string)($_POST['mode'] ?? 'test');
        $allowed   = ['test', 'evening', 'morning', 'weekly_json'];
        if (!in_array($mode, $allowed, true)) $mode = 'test';
        $plannerMode = $mode;

        if (!is_executable($pythonBin)) {
            $plannerError = 'Python venv binary not found or not executable: ' . $pythonBin;
        } else {
            $cmd = sprintf(
                'cd %s && %s -m app.src.cli %s 2>&1',
                escapeshellarg($baseDir),
                escapeshellcmd($pythonBin),
                escapeshellarg($mode)
            );
            $plannerOutput = (string)shell_exec($cmd);
            if (trim($plannerOutput) === '') {
                $plannerError = 'Command returned no output.';
            }
        }
    }

    // --- Config (GUI) -------------------------------------------------
    elseif ($action === 'save_config_gui') {
        $activeTab = 'config_gui';
        $newValues = $values;
        $errors    = [];

        foreach ($CONFIG_SCHEMA as $sectionName => $keys) {
            foreach ($keys as $key => $meta) {
                $fieldName = $sectionName . '__' . $key;
                $type      = $meta['type'] ?? 'string';

                if ($type === 'bool') {
                    $newValues[$sectionName][$key] = isset($_POST[$fieldName]);
                } elseif ($type === 'int') {
                    $raw = $_POST[$fieldName] ?? '';
                    if ($raw === '' && $raw !== '0') { $errors[] = ($meta['label'] ?? $key) . ' is required.'; continue; }
                    $val = filter_var($raw, FILTER_VALIDATE_INT);
                    if ($val === false) { $errors[] = ($meta['label'] ?? $key) . ' must be an integer.'; continue; }
                    if (isset($meta['min']) && $val < $meta['min']) $errors[] = ($meta['label'] ?? $key) . ' must be ≥ ' . $meta['min'] . '.';
                    if (isset($meta['max']) && $val > $meta['max']) $errors[] = ($meta['label'] ?? $key) . ' must be ≤ ' . $meta['max'] . '.';
                    $newValues[$sectionName][$key] = $val;
                } elseif ($type === 'time') {
                    $raw = trim((string)($_POST[$fieldName] ?? ''));
                    if ($raw === '') { $errors[] = ($meta['label'] ?? $key) . ' is required.'; continue; }
                    if (!preg_match('/^\d{2}:\d{2}$/', $raw)) { $errors[] = ($meta['label'] ?? $key) . ' must be in HH:MM format.'; continue; }
                    $newValues[$sectionName][$key] = $raw;
                } else {
                    $raw = trim((string)($_POST[$fieldName] ?? ''));
                    if ($raw === '') { $errors[] = ($meta['label'] ?? $key) . ' is required.'; continue; }
                    $newValues[$sectionName][$key] = $raw;
                }
            }
        }

        $configGuiValues = $newValues;

        if ($errors) {
            $configGuiErrors = $errors;
        } else {
            $toml = build_toml_from_values($CONFIG_SCHEMA, $newValues);
            if (!is_dir(dirname($configPath))) @mkdir(dirname($configPath), 0775, true);

            if (@file_put_contents($configPath, $toml) === false) {
                $configGuiErrors[] = 'Failed to write secrets/commute_config.toml (check permissions).';
            } else {
                $configGuiMessages[] = 'Config saved to secrets/commute_config.toml.';
                $rawConfigText  = $toml;
                $rawConfigError = '';
            }
        }
    }

    // --- Config (raw) -------------------------------------------------
    elseif ($action === 'save_config_raw') {
        $activeTab = 'config_raw';
        $newConfigText = (string)($_POST['config_contents'] ?? '');
        if (trim($newConfigText) === '') {
            $rawConfigError = 'Refusing to save an entirely empty config file.';
        } else {
            if (!is_dir(dirname($configPath))) @mkdir(dirname($configPath), 0775, true);
            if (@file_put_contents($configPath, $newConfigText) === false) {
                $rawConfigError = 'Failed to write secrets/commute_config.toml (check permissions).';
            } else {
                $rawConfigMessage = 'Config saved to secrets/commute_config.toml.';
                $rawConfigText    = $newConfigText;
                $values           = parse_toml_to_values($rawConfigText, $CONFIG_SCHEMA);
                $configGuiValues  = $values;
            }
        }
    }

    // --- Feedback: log comfort ---------------------------------------
    elseif ($action === 'log_comfort') {
        $activeTab = 'feedback';
        comfort_form_from_post($comfortForm);

        $args = [];
        $tsLocal  = trim((string)($_POST['timestamp_local'] ?? 'now'));
        $context  = trim((string)($_POST['context'] ?? 'commute'));
        $leg      = trim((string)($_POST['leg'] ?? ''));
        $activity = trim((string)($_POST['activity'] ?? ''));
        $comfort  = trim((string)($_POST['comfort'] ?? ''));
        $wore     = trim((string)($_POST['wore'] ?? ''));
        $woreLevel = trim((string)($_POST['wore_level'] ?? ''));
        $location = trim((string)($_POST['location'] ?? ''));

        $args[] = '--source'; $args[] = 'web';
        $args[] = '--timestamp-local'; $args[] = ($tsLocal !== '' ? $tsLocal : 'now');
        $args[] = '--context'; $args[] = ($context !== '' ? $context : 'commute');

        if ($leg !== '')      { $args[] = '--leg';      $args[] = $leg; }
        if ($location !== '') { $args[] = '--location'; $args[] = $location; }
        if ($activity !== '') { $args[] = '--activity'; $args[] = $activity; }
        if ($wore !== '')     { $args[] = '--wore';     $args[] = $wore; }
        if ($woreLevel !== '') {
            $wl = (int)$woreLevel;
            if ($wl >= 1 && $wl <= 5) { $args[] = '--wore-level'; $args[] = (string)$wl; }
        }
        if ($comfort !== '')  { $args[] = '--comfort';  $args[] = $comfort; }
        if (!empty($_POST['dry_run'])) $args[] = '--dry-run';

        [$rc, $out] = comfort_run_python($args, $baseDir, $pythonBin);
        $comfortOutput = $out;

        if ($rc === 0) {
            $comfortMessages[] = !empty($_POST['dry_run'])
                ? 'Dry-run complete (no DB insert).'
                : 'Feedback logged to comfort.db.';
        } else {
            $comfortErrors[] = 'Failed to log feedback (python rc=' . $rc . ').';
        }
    }

    // --- Feedback: export full table CSV (POST) -----------------------
    elseif ($action === 'export_feedback_csv') {
        $activeTab = 'feedback';

        $dbPath = $dbPathComfort;
        if (!class_exists('SQLite3')) { http_response_code(500); echo "PHP SQLite3 extension missing."; exit; }
        if (!is_file($dbPath))       { http_response_code(404); echo "comfort.db not found at: " . $dbPath; exit; }

        $desired = [
            'id','timestamp_local','source','context','leg','location','activity','wore_level','wore','comfort',
            'temp_f','feels_like_f','wind_speed_mph','wind_gust_mph','humidity_pct','pop_pct','created_at'
        ];

        try {
            $db = comfort_sqlite_open_ro($dbPath);
            $actual = [];
            $resInfo = $db->query("PRAGMA table_info(comfort_logs)");
            while ($resInfo && ($r = $resInfo->fetchArray(SQLITE3_ASSOC))) {
                if (!empty($r['name'])) $actual[] = (string)$r['name'];
            }
            $cols = array_values(array_filter($desired, fn($c) => in_array($c, $actual, true)));
            if (!$cols) { http_response_code(500); echo "comfort_logs has no recognizable columns."; $db->close(); exit; }

            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="commute_feedback.csv"');

            $out = fopen('php://output', 'w');
            fputcsv($out, $cols);

            $sql = "SELECT " . implode(",", $cols) . " FROM comfort_logs ORDER BY id DESC";
            $res = $db->query($sql);
            while ($res && ($row = $res->fetchArray(SQLITE3_ASSOC))) {
                $line = [];
                foreach ($cols as $c) $line[] = $row[$c] ?? '';
                fputcsv($out, $line);
            }

            fclose($out);
            $db->close();
            exit;

        } catch (Throwable $e) {
            http_response_code(500);
            echo "Export failed: " . $e->getMessage();
            exit;
        }
    }

    // --- Feedback: run comfort_suggest --------------------------------
    elseif ($action === 'run_comfort_suggest') {
        $activeTab = 'feedback';
        [$code, $txt] = comfort_run_suggest($baseDir, $pythonBin);
        $comfortSuggestOutput = $txt;
    }
}

// Always load recent comfort rows (best-effort)
$comfortRecent = comfort_read_recent($dbPathComfort, 25);

// ---------------------------------------------------------------------
// Weekly overview JSON: call CLI and decode
// ---------------------------------------------------------------------
if (is_executable($pythonBin)) {
    $cmdWeekly = sprintf(
    'cd %s && LOG_LEVEL=ERROR %s -m app.src.cli %s 2>&1',
        escapeshellarg($baseDir),
        escapeshellcmd($pythonBin),
        escapeshellarg('weekly_json')
    );
    $weeklyRaw = (string)shell_exec($cmdWeekly);

    if (trim($weeklyRaw) === '') {
        $weeklyOverviewError = 'Weekly overview command returned no output.';
    } else {
        $decoded = json_decode($weeklyRaw, true);
        if (!is_array($decoded) || !isset($decoded['days']) || !is_array($decoded['days'])) {
            $weeklyOverviewError = 'Failed to parse weekly overview JSON from CLI.';
        } else {
            $weeklyOverview = $decoded;
        }
    }
} else {
    $weeklyOverviewError = 'Python venv binary not found or not executable: ' . $pythonBin;
}

// ---------------------------------------------------------------------
// Comfort History query + stats (GET); also supports export via GET
// ---------------------------------------------------------------------
$historyExport = ((string)($_GET['history_export'] ?? '') === '1');
$historyExportLimit = (int)($_GET['history_export_limit'] ?? 5000);
if ($historyExportLimit < 10) $historyExportLimit = 10;
if ($historyExportLimit > 50000) $historyExportLimit = 50000;

if (class_exists('SQLite3') && is_file($dbPathComfort)) {
    try {
        $db = comfort_sqlite_open_ro($dbPathComfort);

        $where = [];
        $bind  = [];

        if ($fromIso !== '') { $where[] = "timestamp_local >= :from_iso"; $bind[':from_iso'] = [$fromIso, SQLITE3_TEXT]; }
        if ($toIso   !== '') { $where[] = "timestamp_local <= :to_iso";   $bind[':to_iso']   = [$toIso, SQLITE3_TEXT]; }

        if ($historyContext !== '') { $where[] = "context = :h_ctx"; $bind[':h_ctx'] = [$historyContext, SQLITE3_TEXT]; }
        if ($historyLeg !== '')     { $where[] = "leg = :h_leg";     $bind[':h_leg'] = [$historyLeg, SQLITE3_TEXT]; }
        if ($historyComfort !== '') { $where[] = "comfort = :h_c";   $bind[':h_c']   = [$historyComfort, SQLITE3_TEXT]; }
        if ($historyWoreLevelI !== null) { $where[] = "wore_level = :h_lvl"; $bind[':h_lvl'] = [(string)$historyWoreLevelI, SQLITE3_TEXT]; }

        $whereSql = $where ? ("WHERE " . implode(" AND ", $where)) : "";

        // Export filtered CSV (GET)
        if ($historyExport) {
            $sqlE = "SELECT id,timestamp_local,source,context,leg,location,activity,wore_level,wore,comfort,temp_f,feels_like_f,wind_speed_mph,wind_gust_mph,humidity_pct,pop_pct,created_at
                     FROM comfort_logs $whereSql
                     ORDER BY id DESC
                     LIMIT :lim";

            $stmtE = $db->prepare($sqlE);
            foreach ($bind as $k => [$v,$t]) $stmtE->bindValue($k, $v, $t);
            $stmtE->bindValue(':lim', $historyExportLimit, SQLITE3_INTEGER);

            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="comfort_history_filtered.csv"');

            $out = fopen('php://output', 'w');
            fputcsv($out, ['id','timestamp_local','source','context','leg','location','activity','wore_level','wore','comfort','temp_f','feels_like_f','wind_speed_mph','wind_gust_mph','humidity_pct','pop_pct','created_at']);

            $resE = $stmtE->execute();
            while ($resE && ($r = $resE->fetchArray(SQLITE3_ASSOC))) {
                fputcsv($out, [
                    $r['id'] ?? '',
                    $r['timestamp_local'] ?? '',
                    $r['source'] ?? '',
                    $r['context'] ?? '',
                    $r['leg'] ?? '',
                    $r['location'] ?? '',
                    $r['activity'] ?? '',
                    $r['wore_level'] ?? '',
                    $r['wore'] ?? '',
                    $r['comfort'] ?? '',
                    $r['temp_f'] ?? '',
                    $r['feels_like_f'] ?? '',
                    $r['wind_speed_mph'] ?? '',
                    $r['wind_gust_mph'] ?? '',
                    $r['humidity_pct'] ?? '',
                    $r['pop_pct'] ?? '',
                    $r['created_at'] ?? '',
                ]);
            }

            fclose($out);
            $db->close();
            exit;
        }

        // History rows
        $sqlH = "SELECT id, timestamp_local, source, context, leg, location, activity, wore_level, wore, comfort,
                        temp_f, feels_like_f, wind_speed_mph, wind_gust_mph, humidity_pct, pop_pct
                 FROM comfort_logs $whereSql
                 ORDER BY timestamp_local DESC
                 LIMIT :lim";

        $stmtH = $db->prepare($sqlH);
        foreach ($bind as $k => [$v,$t]) $stmtH->bindValue($k, $v, $t);
        $stmtH->bindValue(':lim', $historyLimit, SQLITE3_INTEGER);

        $resH = $stmtH->execute();
        while ($resH && ($r = $resH->fetchArray(SQLITE3_ASSOC))) {
            $historyRows[] = $r;
        }

        // Feels-like 10°F bands
        $where2 = $where;
        $bind2  = $bind;
        $where2[] = "feels_like_f IS NOT NULL";
        $whereSql2 = "WHERE " . implode(" AND ", $where2);

        $sqlB = "SELECT (CAST((feels_like_f / 10) AS INTEGER) * 10) AS band_start,
                        COUNT(*) AS n_total,
                        SUM(CASE WHEN lower(comfort) IN ('comfortable','ok') THEN 1 ELSE 0 END) AS n_comfy
                 FROM comfort_logs
                 $whereSql2
                 GROUP BY band_start
                 ORDER BY band_start ASC";

        $stmtB = $db->prepare($sqlB);
        foreach ($bind2 as $k => [$v,$t]) $stmtB->bindValue($k, $v, $t);
        $resB = $stmtB->execute();
        while ($resB && ($r = $resB->fetchArray(SQLITE3_ASSOC))) {
            $bandRows[] = $r;
        }

        $db->close();

    } catch (Throwable $e) {
        $historyErr = $e->getMessage();
        try { if (isset($db) && $db instanceof SQLite3) $db->close(); } catch (Throwable $e2) {}
    }
} else {
    // keep empty; UI will show friendly message
}

// ---------------------------------------------------------------------
// Helpers for tab active classes
// ---------------------------------------------------------------------
function tabButtonClass(string $current, string $tab): string {
  return $current === $tab ? 'tab-btn 2b-tab tab-btn-active' : 'tab-btn 2b-tab';
}
function tabPanelClass(string $current, string $tab): string {
    return $current === $tab ? 'tab-panel tab-panel-active' : 'tab-panel';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Commute Planner Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="stylesheet" href="styles.css?v=<?php echo h((string)(is_file(__DIR__ . '/styles.css') ? filemtime(__DIR__ . '/styles.css') : time())); ?>" />
</head>
<body>
  <div class="page">
    <div class="shell">
      <div class="inner">
        <header>
          <div class="title-block">
            <a class="lab-link" href="/">&larr; Lab</a>
            <div class="chip 2b-chip">Commute Plan</div>
            <h1>Tulsa Walking Dashboard</h1>
            <div class="subtitle">
              See what tomorrow looks like, nudge departure times, and tweak thresholds without touching the shell.
            </div>
          </div>
          <div class="status-pill 2b-badge">
            <span class="status-dot"></span>
            Local-only · Dark mode
          </div>
        </header>

        <div class="tab-nav">
          <button class="<?php echo h(tabButtonClass($activeTab, 'planner')); ?>" type="button" data-tab="planner" onclick="switchTab('planner')">
            <span class="icon">🧠</span> Planner
          </button>
          <button class="<?php echo h(tabButtonClass($activeTab, 'config_gui')); ?>" type="button" data-tab="config_gui" onclick="switchTab('config_gui')">
            <span class="icon">🎛️</span> Config (GUI)
          </button>
          <button class="<?php echo h(tabButtonClass($activeTab, 'config_raw')); ?>" type="button" data-tab="config_raw" onclick="switchTab('config_raw')">
            <span class="icon">📄</span> Config (raw)
          </button>
          <button class="<?php echo h(tabButtonClass($activeTab, 'feedback')); ?>" type="button" data-tab="feedback" onclick="switchTab('feedback')">
            <span class="icon">📝</span> Feedback
          </button>
        </div>

        <!-- Tab: Planner -->
        <div class="<?php echo h(tabPanelClass($activeTab, 'planner')); ?>" id="tab-panel-planner">
          <div class="grid-2">
            <div class="card 2b-card">
              <div class="card-header">
                <div>
                  <div class="card-title"><span class="icon">🧠</span> Planner preview</div>
                  <div class="card-subtitle">Run the CLI and see exactly what it would send to Discord.</div>
                </div>
                <div class="badge 2b-badge"><span class="badge-dot" style="background: var(--accent2);"></span> venv · app.src.cli</div>
              </div>

              <form method="post" style="position:relative; z-index:1;">
                <div class="mode-group">
                  <label><input type="radio" name="mode" value="test" <?php echo ($plannerMode === 'test' || $plannerMode === '') ? 'checked' : ''; ?> /> <span>Test</span></label>
                  <label><input type="radio" name="mode" value="evening" <?php echo ($plannerMode === 'evening') ? 'checked' : ''; ?> /> <span>Evening</span></label>
                  <label><input type="radio" name="mode" value="morning" <?php echo ($plannerMode === 'morning') ? 'checked' : ''; ?> /> <span>Morning</span></label>
                  <label><input type="radio" name="mode" value="weekly_json" <?php echo ($plannerMode === 'weekly_json') ? 'checked' : ''; ?> /> <span>Weekly JSON</span></label>
                </div>

                <div class="helper-text">
                  <code>test</code>: show config + paths only.<br />
                  <code>evening</code>: tomorrow’s commute windows.<br />
                  <code>morning</code>: today’s commute using minutely POP refinement.<br />
                  <code>weekly_json</code>: JSON weekly overview for the dashboard.
                </div>

                <div style="margin-top:10px; display:flex; align-items:center; justify-content:space-between; gap:8px;">
                  <div class="helper-text">Uses <code>venv/bin/python -m app.src.cli &lt;mode&gt;</code>.</div>
                  <div>
                    <input type="hidden" name="csrf_token" value="<?php echo h($csrfToken); ?>" />
                    <input type="hidden" name="tab" value="planner" id="planner-tab-input" />
                    <button type="submit" name="action" value="run_plan" class="btn btn-secondary">Run planner ▶</button>
                  </div>
                </div>

                <?php if ($plannerError || $plannerOutput): ?>
                  <div style="margin-top:10px;">
                    <div class="output-label">
                      <?php if ($plannerError): ?>
                        <span style="color: var(--error);">Result (<?php echo h($plannerMode ?: 'test'); ?>):</span>
                      <?php else: ?>
                        <span style="color: var(--accent);">Result (<?php echo h($plannerMode ?: 'test'); ?>):</span>
                      <?php endif; ?>
                    </div>
                    <div class="output-block">
                      <?php if ($plannerError): ?>
                        ⚠️ <?php echo h($plannerError); ?><?php if ($plannerOutput) echo "\n\n" . h($plannerOutput); ?>
                      <?php else: ?>
                        <?php echo h($plannerOutput); ?>
                      <?php endif; ?>
                    </div>
                  </div>
                <?php endif; ?>
              </form>
            </div>

            <div class="card 2b-card">
              <div class="card-header">
                <div>
                  <div class="card-title"><span class="icon">��</span> Weekly overview</div>
                  <div class="card-subtitle">Emoji dashboard for the next few days using your commute windows.</div>
                </div>
                <div class="badge 2b-badge"><span class="badge-dot"></span> hourly · build_week_overview</div>
              </div>

              <div style="position:relative; z-index:1;">
                <?php if ($weeklyOverviewError): ?>
                  <div class="messages"><div class="msg-error">⚠️ <?php echo h($weeklyOverviewError); ?></div></div>
                <?php elseif ($weeklyOverview && isset($weeklyOverview['days']) && is_array($weeklyOverview['days'])): ?>
                  <div class="helper-text" style="margin-bottom:8px;">
                    Clothing: 🧥 heavy coat · 🧶 light jacket · 👕 tee/long-sleeve · 🩳👕 shorts.<br />
                    Walk: ✅ ok · ⚠️ borderline/caution · 🚫 probably drive.
                  </div>

                  <div class="table-wrap">
                    <table class="table" style="min-width: 520px;">
                      <thead>
                        <tr>
                          <th style="width:140px;">Day</th>
                          <th>AM</th>
                          <th>PM</th>
                        </tr>
                      </thead>
                      <tbody>
                        <?php foreach ($weeklyOverview['days'] as $day): ?>
                          <?php
                            $weekday   = $day['weekday'] ?? '?';
                            $dateStr   = $day['date'] ?? '';
                            $morning   = is_array($day['morning'] ?? null) ? $day['morning'] : null;
                            $afternoon = is_array($day['afternoon'] ?? null) ? $day['afternoon'] : null;

                            $renderSlot = function (?array $slot) {
                              if (!is_array($slot)) { echo '<span style="color: var(--text-muted);">—</span>'; return; }

                              $outer    = $slot['outerwear'] ?? null;
                              $score    = $slot['walk_score'] ?? null;
                              $leave    = (string)($slot['leave_time_local'] ?? '');
                              $tempF    = $slot['temp_f'] ?? null;
                              $feelsF   = $slot['feels_like_f'] ?? null;
                              $pop      = $slot['pop'] ?? null;
                              $windSpd  = $slot['wind_speed_mph'] ?? null;
                              $windGust = $slot['wind_gust_mph'] ?? null;

                              $outerEmoji = commute_outerwear_emoji($outer);
                              $walkEmoji  = commute_walk_emoji($score);

                              $tempLine = '';
                              if ($tempF !== null && $feelsF !== null) {
                                $tempLine = sprintf('%d°F (feels %d°F)', (int)round((float)$tempF), (int)round((float)$feelsF));
                              } elseif ($tempF !== null) {
                                $tempLine = sprintf('%d°F', (int)round((float)$tempF));
                              }

                              $metaParts = [];
                              if ($leave !== '') $metaParts[] = 'Leave ' . $leave;
                              if ($pop !== null) $metaParts[] = sprintf('POP %d%%', (int)$pop);
                              if ($windSpd !== null && $windGust !== null) {
                                $metaParts[] = sprintf('wind %d mph (gusts %d)', (int)round((float)$windSpd), (int)round((float)$windGust));
                              } elseif ($windSpd !== null) {
                                $metaParts[] = sprintf('wind %d mph', (int)round((float)$windSpd));
                              }

                              echo '<div style="display:flex; flex-direction:column; gap:2px;">';
                              echo '<div style="font-size:1.05rem;">' . h($outerEmoji . ' ' . $walkEmoji) . '</div>';
                              if ($tempLine !== '') echo '<div style="font-size:0.74rem;">' . h($tempLine) . '</div>';
                              if ($metaParts) echo '<div style="font-size:0.7rem; color: var(--text-muted);">' . h(implode(' · ', $metaParts)) . '</div>';
                              echo '</div>';
                            };
                          ?>
                          <tr>
                            <td>
                              <div style="display:flex; flex-direction:column;">
                                <span><?php echo h($weekday); ?></span>
                                <?php if ($dateStr): ?>
                                  <span style="font-size:0.72rem; color: var(--text-muted);"><?php echo h($dateStr); ?></span>
                                <?php endif; ?>
                              </div>
                            </td>
                            <td><?php $renderSlot($morning); ?></td>
                            <td><?php $renderSlot($afternoon); ?></td>
                          </tr>
                        <?php endforeach; ?>
                      </tbody>
                    </table>
                  </div>
                <?php else: ?>
                  <div class="messages"><div class="msg-error">⚠️ No weekly overview data available.</div></div>
                <?php endif; ?>
              </div>
            </div>
          </div>
        </div>

        <!-- Tab: Config (GUI) -->
        <div class="<?php echo h(tabPanelClass($activeTab, 'config_gui')); ?>" id="tab-panel-config_gui">
          <div class="card 2b-card">
            <div class="card-header">
              <div>
                <div class="card-title"><span class="icon">🎛️</span> Commute config (GUI)</div>
                <div class="card-subtitle">Adjust thresholds, POP limits, minutely refinement, and alert behavior.</div>
              </div>
              <div class="badge 2b-badge"><span class="badge-dot"></span> secrets/commute_config.toml</div>
            </div>

            <form method="post" style="position:relative; z-index:1;">
              <div class="config-grid">
                <?php foreach ($CONFIG_SCHEMA as $sectionName => $keys): ?>
                  <?php foreach ($keys as $key => $meta): ?>
                    <?php
                      $fieldName = $sectionName . '__' . $key;
                      $label     = $meta['label'] ?? ($sectionName . '.' . $key);
                      $type      = $meta['type'] ?? 'string';
                      $comment   = $meta['comment'] ?? '';
                      $val       = $configGuiValues[$sectionName][$key] ?? ($meta['default'] ?? null);
                    ?>
                    <div class="config-field">
                      <?php if ($type === 'bool'): ?>
                        <label class="config-checkbox">
                          <input type="checkbox" name="<?php echo h($fieldName); ?>" <?php echo $val ? 'checked' : ''; ?> />
                          <span><?php echo h($label); ?></span>
                        </label>
                        <?php if ($comment): ?><div class="config-comment"><?php echo h($comment); ?></div><?php endif; ?>
                      <?php else: ?>
                        <div class="config-label"><?php echo h($label); ?></div>
                        <input
                          class="config-input"
                          type="<?php echo $type === 'int' ? 'number' : 'text'; ?>"
                          name="<?php echo h($fieldName); ?>"
                          value="<?php echo h((string)$val); ?>"
                          <?php if ($type === 'int' && isset($meta['min'])): ?>min="<?php echo h((string)$meta['min']); ?>"<?php endif; ?>
                          <?php if ($type === 'int' && isset($meta['max'])): ?>max="<?php echo h((string)$meta['max']); ?>"<?php endif; ?>
                        />
                        <?php if ($comment): ?><div class="config-comment"><?php echo h($comment); ?></div><?php endif; ?>
                      <?php endif; ?>
                    </div>
                  <?php endforeach; ?>
                <?php endforeach; ?>
              </div>

              <div class="messages">
                <?php foreach ($configGuiMessages as $msg): ?><div class="msg-success">✅ <?php echo h($msg); ?></div><?php endforeach; ?>
                <?php foreach ($configGuiErrors as $err): ?><div class="msg-error">⚠️ <?php echo h($err); ?></div><?php endforeach; ?>
              </div>

              <div style="margin-top:10px; display:flex; align-items:center; justify-content:space-between; gap:8px;">
                <div class="helper-text">
                  This form rewrites <code>secrets/commute_config.toml</code> using a canonical layout.<br />
                  Any unknown keys in the old file will be dropped (raw editor is still available).
                </div>
                <div>
                  <input type="hidden" name="csrf_token" value="<?php echo h($csrfToken); ?>" />
                  <input type="hidden" name="tab" value="config_gui" id="config-gui-tab-input" />
                  <button type="submit" name="action" value="save_config_gui" class="btn btn-primary">Save GUI config 💾</button>
                </div>
              </div>
            </form>
          </div>
        </div>

        <!-- Tab: Config (raw) -->
        <div class="<?php echo h(tabPanelClass($activeTab, 'config_raw')); ?>" id="tab-panel-config_raw">
          <div class="card 2b-card">
            <div class="card-header">
              <div>
                <div class="card-title"><span class="icon">📄</span> Commute config (raw TOML)</div>
                <div class="card-subtitle">Full control for pasting/editing your config.</div>
              </div>
              <div class="badge 2b-badge"><span class="badge-dot"></span> TOML editor</div>
            </div>

            <form method="post" style="position:relative; z-index:1;">
              <textarea name="config_contents" spellcheck="false"><?php echo h($rawConfigText); ?></textarea>

              <div class="messages">
                <?php if ($rawConfigMessage): ?><div class="msg-success">✅ <?php echo h($rawConfigMessage); ?></div><?php endif; ?>
                <?php if ($rawConfigError): ?><div class="msg-error">⚠️ <?php echo h($rawConfigError); ?></div><?php endif; ?>
              </div>

              <div style="margin-top:10px; display:flex; align-items:center; justify-content:space-between; gap:8px;">
                <div class="helper-text">
                  Writes directly to <code>secrets/commute_config.toml</code>. GUI refreshes from whatever you save here.
                </div>
                <div>
                  <input type="hidden" name="csrf_token" value="<?php echo h($csrfToken); ?>" />
                  <input type="hidden" name="tab" value="config_raw" id="config-raw-tab-input" />
                  <button type="submit" name="action" value="save_config_raw" class="btn btn-secondary">Save raw config 💾</button>
                </div>
              </div>
            </form>
          </div>
        </div>

        <!-- Tab: Feedback -->
        <div class="<?php echo h(tabPanelClass($activeTab, 'feedback')); ?>" id="tab-panel-feedback">
          <div class="card 2b-card">
            <div class="card-header">
              <div>
                <div class="card-title"><span class="icon">📝</span> Comfort feedback</div>
                <div class="card-subtitle">Log how it felt + what you wore; stores nearest hourly snapshot alongside notes.</div>
              </div>
              <div class="badge 2b-badge"><span class="badge-dot" style="background: var(--accent2);"></span> data/comfort.db · comfort_cli</div>
            </div>

            <form method="post" style="position:relative; z-index:1;">
              <div class="config-grid">
                <div class="config-field">
                  <div class="config-label">Timestamp (local)</div>
                  <input class="config-input" type="text" name="timestamp_local" value="<?php echo h($comfortForm['timestamp_local']); ?>" />
                  <div class="config-comment">Use <code>now</code> or ISO like <code>2025-12-12T07:05</code></div>
                </div>

                <div class="config-field">
                  <div class="config-label">Context</div>
                  <input class="config-input" type="text" name="context" value="<?php echo h($comfortForm['context']); ?>" />
                  <div class="config-comment">Examples: <code>commute</code>, <code>laps</code>, <code>errand</code></div>
                </div>

                <div class="config-field">
                  <div class="config-label">Leg (optional)</div>
                  <input class="config-input" type="text" name="leg" value="<?php echo h($comfortForm['leg']); ?>" />
                  <div class="config-comment">Examples: <code>morning</code>, <code>afternoon</code>, <code>lunch</code></div>
                </div>

                <div class="config-field">
                  <div class="config-label">Activity (optional)</div>
                  <input class="config-input" type="text" name="activity" value="<?php echo h($comfortForm['activity']); ?>" />
                  <div class="config-comment">Examples: <code>walked</code>, <code>drove</code>, <code>laps</code></div>
                </div>

                <div class="config-field">
                  <div class="config-label">Comfort (optional)</div>
                  <input class="config-input" type="text" name="comfort" value="<?php echo h($comfortForm['comfort']); ?>" />
                  <div class="config-comment">Examples: <code>ok</code>, <code>comfortable</code>, <code>too_cold</code>, <code>windy</code></div>
                </div>

                <div class="config-field">
                  <div class="config-label">What you wore (optional)</div>
                  <input class="config-input" type="text" name="wore" value="<?php echo h($comfortForm['wore']); ?>" />
                  <div class="config-comment">Free text: <code>t-shirt + hoodie</code>, <code>light jacket</code>, etc.</div>

                  <div class="config-label" style="margin-top:10px;">Wear level (optional)</div>
                  <select class="config-input" name="wore_level">
                    <?php $wl = (string)($comfortForm['wore_level'] ?? ''); ?>
                    <option value="" <?php echo ($wl===''?'selected':''); ?>>—</option>
                    <option value="1" <?php echo ($wl==='1'?'selected':''); ?>>1 — short sleeve (no jacket)</option>
                    <option value="2" <?php echo ($wl==='2'?'selected':''); ?>>2 — long sleeve</option>
                    <option value="3" <?php echo ($wl==='3'?'selected':''); ?>>3 — long sleeve + undershirt</option>
                    <option value="4" <?php echo ($wl==='4'?'selected':''); ?>>4 — + jacket/coat</option>
                    <option value="5" <?php echo ($wl==='5'?'selected':''); ?>>5 — coat + gloves + hat + scarf</option>
                  </select>

                  <div class="helper-text" style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
                    <?php for ($i=1; $i<=5; $i++): ?>
                      <button type="button" class="btn btn-secondary" style="padding:6px 10px;"
                        onclick="(function(){var el=document.querySelector('select[name=&quot;wore_level&quot;]'); if(el){el.value='<?php echo $i; ?>';}})();">
                        <?php echo h("L".$i); ?>
                      </button>
                    <?php endfor; ?>
                    <span>Quick pick (L1–L5)</span>
                  </div>
                </div>

                <div class="config-field">
                  <div class="config-label">Location (optional)</div>
                  <input class="config-input" type="text" name="location" value="<?php echo h($comfortForm['location']); ?>" />
                  <div class="config-comment">Example: <code>work</code>, <code>home</code>, <code>parking lot</code></div>
                </div>

                <div class="config-field">
                  <label class="config-checkbox">
                    <input type="checkbox" name="dry_run" <?php echo !empty($comfortForm['dry_run']) ? 'checked' : ''; ?> />
                    <span>Dry-run (do not insert)</span>
                  </label>
                  <div class="config-comment">Print what would be logged, but skip DB insert.</div>
                </div>
              </div>

              <div class="messages">
                <?php foreach ($comfortMessages as $msg): ?><div class="msg-success">✅ <?php echo h($msg); ?></div><?php endforeach; ?>
                <?php foreach ($comfortErrors as $err): ?><div class="msg-error">⚠️ <?php echo h($err); ?></div><?php endforeach; ?>
              </div>

              <div style="margin-top:10px; display:flex; align-items:center; justify-content:space-between; gap:8px;">
                <div class="helper-text">
                  Runs <code>venv/bin/python -m app.src.comfort_cli</code> (source=<code>web</code>) → <code>data/comfort.db</code>
                </div>
                <div>
                  <input type="hidden" name="csrf_token" value="<?php echo h($csrfToken); ?>" />
                  <input type="hidden" name="tab" value="feedback" id="feedback-tab-input" />
                  <button type="submit" name="action" value="log_comfort" class="btn btn-primary">Save feedback 💾</button>
                </div>
              </div>

              <?php if (!empty($comfortOutput)): ?>
                <div style="margin-top:10px;">
                  <div class="output-label"><span style="color: var(--accent);">Python output:</span></div>
                  <div class="output-block"><?php echo h($comfortOutput); ?></div>
                </div>
              <?php endif; ?>
            </form>
          </div>

          <div class="card 2b-card" style="margin-top:12px;">
            <div class="card-header">
              <div>
                <div class="card-title"><span class="icon">🧾</span> Recent feedback</div>
                <div class="card-subtitle">Latest 25 rows from <code>comfort_logs</code>.</div>
              </div>
              <div class="badge 2b-badge"><span class="badge-dot"></span> export + table</div>
            </div>

            <form method="post" style="margin-top:6px; position:relative; z-index:1;">
              <input type="hidden" name="csrf_token" value="<?php echo h($csrfToken); ?>" />
              <input type="hidden" name="tab" value="feedback" />
              <button type="submit" name="action" value="export_feedback_csv" class="btn btn-secondary">Export full CSV ⬇️</button>
              <span class="helper-text" style="margin-left:8px;">Exports the full table (all rows).</span>
            </form>

            <?php if (!empty($comfortRecent) && isset($comfortRecent[0]['__error'])): ?>
              <div class="messages" style="margin-top:8px;"><div class="msg-error">⚠️ <?php echo h($comfortRecent[0]['__error']); ?></div></div>
            <?php elseif (empty($comfortRecent)): ?>
              <div class="messages" style="margin-top:8px;"><div class="msg-error">⚠️ No feedback rows yet.</div></div>
            <?php else: ?>
              <div class="table-wrap" style="margin-top:10px;">
                <table class="table table-compact">
                  <thead>
                    <tr>
                      <th class="nowrap">ID</th>
                      <th class="nowrap">When</th>
                      <th>Context</th>
                      <th>Leg</th>
                      <th>Activity</th>
                      <th>Comfort</th>
                      <th>Wore</th>
                      <th class="nowrap">Level</th>
                      <th class="nowrap">Temp</th>
                      <th class="nowrap">Feels</th>
                      <th class="nowrap">Wind</th>
                      <th class="nowrap">Gust</th>
                      <th class="nowrap">Hum</th>
                      <th class="nowrap">POP</th>
                    </tr>
                  </thead>
                  <tbody>
                    <?php foreach ($comfortRecent as $r): ?>
                      <?php
                        $lvl = (string)($r['wore_level'] ?? '');
                        $lbl = wore_level_label($lvl);
                        $c = (string)($r['comfort'] ?? '');
                        $ce = $c !== '' ? comfort_emoji($c) : '';
                      ?>
                      <tr>
                        <td class="nowrap"><?php echo h((string)($r['id'] ?? '')); ?></td>
                        <td class="nowrap"><code><?php echo h((string)($r['timestamp_local'] ?? '')); ?></code></td>
                        <td><?php echo h((string)($r['context'] ?? '')); ?></td>
                        <td><?php echo h((string)($r['leg'] ?? '')); ?></td>
                        <td><?php echo h((string)($r['activity'] ?? '')); ?></td>
                        <td><?php echo h(trim(($ce ? ($ce.' ') : '').$c)); ?></td>
                        <td><?php echo h((string)($r['wore'] ?? '')); ?></td>
                        <td class="nowrap"><?php echo h($lbl !== '' ? $lbl : $lvl); ?></td>
                        <td class="nowrap"><?php echo h((string)($r['temp_f'] ?? '')); ?></td>
                        <td class="nowrap"><?php echo h((string)($r['feels_like_f'] ?? '')); ?></td>
                        <td class="nowrap"><?php echo h((string)($r['wind_speed_mph'] ?? '')); ?></td>
                        <td class="nowrap"><?php echo h((string)($r['wind_gust_mph'] ?? '')); ?></td>
                        <td class="nowrap"><?php echo h((string)($r['humidity_pct'] ?? '')); ?></td>
                        <td class="nowrap"><?php echo h((string)($r['pop_pct'] ?? '')); ?></td>
                      </tr>
                    <?php endforeach; ?>
                  </tbody>
                </table>
              </div>
            <?php endif; ?>
          </div>

          <div class="card 2b-card" style="margin-top:12px;" id="comfort-history">
            <div class="card-header">
              <div>
                <div class="card-title"><span class="icon">📚</span> Comfort history</div>
                <div class="card-subtitle">Filter by date/context and export a filtered CSV.</div>
              </div>
              <div class="badge 2b-badge"><span class="badge-dot"></span> server-side filter</div>
            </div>

            <form method="get" style="position:relative; z-index:1; margin-top:6px;">
              <input type="hidden" name="tab" value="feedback" />
              <div class="config-grid">
                <div class="config-field">
                  <div class="config-label">From (YYYY-MM-DD)</div>
                  <input class="config-input" type="date" name="history_from" value="<?php echo h($historyFrom); ?>" />
                </div>
                <div class="config-field">
                  <div class="config-label">To (YYYY-MM-DD)</div>
                  <input class="config-input" type="date" name="history_to" value="<?php echo h($historyTo); ?>" />
                </div>
                <div class="config-field">
                  <div class="config-label">Max rows</div>
                  <input class="config-input" type="number" name="history_limit" min="10" max="2000" step="10" value="<?php echo h((string)$historyLimit); ?>" />
                  <div class="config-comment">Leave dates blank to show the most recent rows.</div>
                </div>

                <div class="config-field">
                  <div class="config-label">Context (optional)</div>
                  <input class="config-input" type="text" name="history_context" placeholder="commute / laps / errand..." value="<?php echo h($historyContext); ?>" />
                </div>

                <div class="config-field">
                  <div class="config-label">Leg (optional)</div>
                  <input class="config-input" type="text" name="history_leg" placeholder="morning / afternoon..." value="<?php echo h($historyLeg); ?>" />
                </div>

                <div class="config-field">
                  <div class="config-label">Comfort (optional)</div>
                  <select class="config-input" name="history_comfort">
                    <?php
                      $opts = ['', 'too_cold','a_bit_cold','comfortable','a_bit_hot','too_hot','ok'];
                      foreach ($opts as $o) {
                        $sel = ($o === $historyComfort) ? ' selected' : '';
                        $label = ($o === '') ? '(any)' : $o;
                        echo '<option value="' . h($o) . '"' . $sel . '>' . h($label) . '</option>';
                      }
                    ?>
                  </select>
                </div>

                <div class="config-field">
                  <div class="config-label">Wear level (optional)</div>
                  <select class="config-input" name="history_wore_level">
                    <?php
                      $lvlOpts = ['', '1','2','3','4','5'];
                      $curLvl = (string)($historyWoreLevelI ?? '');
                      foreach ($lvlOpts as $o) {
                        $sel = ($o === $curLvl) ? ' selected' : '';
                        $label = ($o === '') ? '(any)' : ("Level " . $o);
                        echo '<option value="' . h($o) . '"' . $sel . '>' . h($label) . '</option>';
                      }
                    ?>
                  </select>
                </div>
              </div>

              <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
                <button type="submit" class="btn btn-secondary">Apply filter</button>
                <a class="btn btn-secondary" href="<?php echo h(strtok($_SERVER["REQUEST_URI"], "?")); ?>?tab=feedback#comfort-history"
                   style="text-decoration:none; display:inline-flex; align-items:center;">Reset</a>

                <span style="flex:1;"></span>

                <button class="btn btn-secondary" type="submit" name="history_export" value="1">Export filtered CSV ⬇️</button>
                <input type="hidden" name="history_export_limit" value="5000" />
              </div>
            </form>

            <?php if ($historyErr): ?>
              <div class="messages" style="margin-top:8px;"><div class="msg-error">⚠️ History query error: <?php echo h($historyErr); ?></div></div>
            <?php endif; ?>

            <?php if (!class_exists('SQLite3') || !is_file($dbPathComfort)): ?>
              <div class="messages" style="margin-top:10px;"><div class="msg-error">⚠️ No comfort DB available yet at: <?php echo h($dbPathComfort); ?></div></div>
            <?php else: ?>
              <div class="table-wrap" style="margin-top:10px;">
                <table class="table table-compact">
                  <thead>
                    <tr>
                      <th class="nowrap">Time</th>
                      <th>Ctx</th>
                      <th>Leg</th>
                      <th>Loc</th>
                      <th>Act</th>
                      <th>Comfort</th>
                      <th class="nowrap">Level</th>
                      <th>Wore</th>
                      <th class="nowrap">Temp</th>
                      <th class="nowrap">Feels</th>
                      <th class="nowrap">Wind</th>
                      <th class="nowrap">Gust</th>
                      <th class="nowrap">Hum</th>
                      <th class="nowrap">POP</th>
                      <th class="nowrap">Src</th>
                    </tr>
                  </thead>
                  <tbody>
                    <?php if (!$historyRows): ?>
                      <tr><td colspan="15" class="helper-text">No history rows match your filter.</td></tr>
                    <?php else: ?>
                      <?php foreach ($historyRows as $r): ?>
                        <?php
                          $c=(string)($r['comfort'] ?? '');
                          $ce=$c !== '' ? comfort_emoji($c) : '';
                        ?>
                        <tr>
                          <td class="nowrap"><?php echo h((string)($r['timestamp_local'] ?? '')); ?></td>
                          <td><?php echo h((string)($r['context'] ?? '')); ?></td>
                          <td><?php echo h((string)($r['leg'] ?? '')); ?></td>
                          <td><?php echo h((string)($r['location'] ?? '')); ?></td>
                          <td><?php echo h((string)($r['activity'] ?? '')); ?></td>
                          <td><?php echo h(trim(($ce ? ($ce.' ') : '').$c)); ?></td>
                          <td class="nowrap"><?php echo h((string)($r['wore_level'] ?? '')); ?></td>
                          <td><?php echo h((string)($r['wore'] ?? '')); ?></td>
                          <td class="nowrap"><?php echo h((string)($r['temp_f'] ?? '')); ?></td>
                          <td class="nowrap"><?php echo h((string)($r['feels_like_f'] ?? '')); ?></td>
                          <td class="nowrap"><?php echo h((string)($r['wind_speed_mph'] ?? '')); ?></td>
                          <td class="nowrap"><?php echo h((string)($r['wind_gust_mph'] ?? '')); ?></td>
                          <td class="nowrap"><?php echo h((string)($r['humidity_pct'] ?? '')); ?></td>
                          <td class="nowrap"><?php echo h((string)($r['pop_pct'] ?? '')); ?></td>
                          <td class="nowrap"><?php echo h((string)($r['source'] ?? '')); ?></td>
                        </tr>
                      <?php endforeach; ?>
                    <?php endif; ?>
                  </tbody>
                </table>
              </div>

              <div class="card 2b-card" style="margin-top:12px; padding:12px;">
                <div class="card-title" style="margin-bottom:6px;">Comfort by feels-like (10°F bands)</div>
                <div class="helper-text" style="margin-bottom:8px;">
                  “Comfy%” counts only comfort=comfortable|ok (baseline). As you log more, we can expand this.
                </div>

                <div class="table-wrap">
                  <table class="table" style="min-width: 520px;">
                    <thead>
                      <tr>
                        <th class="nowrap">Band (°F)</th>
                        <th class="nowrap">Total</th>
                        <th class="nowrap">Comfy</th>
                        <th class="nowrap">Comfy%</th>
                      </tr>
                    </thead>
                    <tbody>
                      <?php if (!$bandRows): ?>
                        <tr><td colspan="4" class="helper-text">Not enough data yet (or no feels-like values in this range).</td></tr>
                      <?php else: ?>
                        <?php foreach ($bandRows as $b): ?>
                          <?php
                            $bs = (int)($b['band_start'] ?? 0);
                            $be = $bs + 9;
                            $nt = (int)($b['n_total'] ?? 0);
                            $nc = (int)($b['n_comfy'] ?? 0);
                            $pct = ($nt > 0) ? round(($nc / $nt) * 100.0, 1) : 0.0;
                          ?>
                          <tr>
                            <td class="nowrap"><?php echo h($bs . "–" . $be); ?></td>
                            <td class="nowrap"><?php echo h((string)$nt); ?></td>
                            <td class="nowrap"><?php echo h((string)$nc); ?></td>
                            <td class="nowrap"><?php echo h((string)$pct); ?>%</td>
                          </tr>
                        <?php endforeach; ?>
                      <?php endif; ?>
                    </tbody>
                  </table>
                </div>

                <div class="helper-text" style="margin-top:8px;">
                  Tip: leave dates blank to show the most recent rows (limited by “Max rows”).
                </div>
              </div>
            <?php endif; ?>
          </div>

          <div class="card 2b-card" style="margin-top:12px;">
            <div class="card-header">
              <div>
                <div class="card-title"><span class="icon">🧠</span> Comfort suggestions</div>
                <div class="card-subtitle">Uses your logged comfort data to suggest threshold tweaks (Phase 5).</div>
              </div>
              <div class="badge 2b-badge"><span class="badge-dot"></span> comfort_suggest</div>
            </div>

            <form method="post" style="margin-top:10px; position:relative; z-index:1;">
              <input type="hidden" name="csrf_token" value="<?php echo h($csrfToken); ?>" />
              <input type="hidden" name="tab" value="feedback" />
              <button class="btn btn-secondary" type="submit" name="action" value="run_comfort_suggest">Run comfort_suggest</button>
              <span class="helper-text" style="margin-left:8px;">
                Tip: you need a few logs with <code>wore_level</code> + <code>comfort=ok</code>/<code>comfortable</code>.
              </span>
            </form>

            <?php if (!empty($comfortSuggestOutput)): ?>
              <div class="helper-text" style="margin-top:12px;">Output:</div>
              <div class="output-block"><?php echo h((string)$comfortSuggestOutput); ?></div>
            <?php endif; ?>

            <details style="margin-top:12px; position:relative; z-index:1;">
              <summary class="helper-text">Quick-start: what to log (examples)</summary>
              <div class="helper-text" style="margin-top:8px;">
                Aim for 5–10 entries across different temps. Use <code>wore_level</code> for consistency.
              </div>
              <div class="output-block" style="margin-top:8px;">
CLI:
  ./venv/bin/python -m app.src.comfort_cli --context commute --leg morning --activity walked --comfort a_bit_cold --wore-level 4 --wore "hoodie + coat"

Discord DM:
  !log context=commute leg=morning activity=walked comfort=a_bit_cold lvl4 wore="hoodie + coat"
  !log context=commute leg=afternoon activity=walked comfort=comfortable lvl3 wore="long sleeve + undershirt"
              </div>
            </details>
          </div>
        </div>

      </div>
    </div>
  </div>

  <script src="app.js?v=<?php echo h((string)(is_file(__DIR__ . '/app.js') ? filemtime(__DIR__ . '/app.js') : time())); ?>"></script>
</body>
</html>
