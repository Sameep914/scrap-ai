param(
    [string]$OutputDirectory = "research/inputs/external"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$demolitionUrl = "https://www.alangtoday.com/all-demolition.aspx"
$analysisUrl = "https://www.alangtoday.com/alang-analysis.aspx"
$acquisitionInstant = [DateTime]::UtcNow
$acquiredAtUtc = $acquisitionInstant.ToString("yyyy-MM-ddTHH:mm:ssZ")
$snapshotId = $acquisitionInstant.ToString("yyyyMMddTHHmmssZ")
$currentYear = $acquisitionInstant.Year
$currentMonth = $acquisitionInstant.Month

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

function Get-HiddenForm {
    param([string]$Html)

    $form = @{}
    $pattern = '<input[^>]+type="hidden"[^>]+name="(?<name>[^"]+)"[^>]+value="(?<value>[^"]*)"[^>]*>'
    foreach ($match in [regex]::Matches($Html, $pattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
        $name = [Net.WebUtility]::HtmlDecode($match.Groups["name"].Value)
        $value = [Net.WebUtility]::HtmlDecode($match.Groups["value"].Value)
        $form[$name] = $value
    }
    return $form
}

function ConvertFrom-DemolitionPage {
    param(
        [string]$Html,
        [int]$PageNumber
    )

    $body = [regex]::Match(
        $Html,
        'id="demolition-table".*?<tbody>(?<body>.*?)</tbody>',
        [Text.RegularExpressions.RegexOptions]::Singleline
    ).Groups["body"].Value

    $ordinal = 0
    foreach ($match in [regex]::Matches($body, '<tr>(?<row>.*?)</tr>', [Text.RegularExpressions.RegexOptions]::Singleline)) {
        $row = $match.Groups["row"].Value
        $recordId = [regex]::Match($row, 'hdnshipid"[^>]*value="(?<value>[^"]*)"').Groups["value"].Value
        if (-not $recordId) {
            continue
        }

        $ordinal += 1
        $nameHtml = [regex]::Match(
            $row,
            'shipdetail"[^>]*>(?<value>.*?)</a>',
            [Text.RegularExpressions.RegexOptions]::Singleline
        ).Groups["value"].Value
        $name = [Net.WebUtility]::HtmlDecode(([regex]::Replace($nameHtml, '<[^>]+>', ''))).Trim()

        $cells = @{}
        $cellPattern = '_td(?<number>\d+)" class="lblData">(?<value>.*?)</td>'
        foreach ($cell in [regex]::Matches($row, $cellPattern, [Text.RegularExpressions.RegexOptions]::Singleline)) {
            $clean = [regex]::Replace($cell.Groups["value"].Value, '<[^>]+>', '')
            $cells[$cell.Groups["number"].Value] = [Net.WebUtility]::HtmlDecode($clean).Trim()
        }

        [pscustomobject]@{
            acquired_at_utc                         = $acquiredAtUtc
            source_url                              = $demolitionUrl
            source_page                             = $PageNumber
            source_row_ordinal                      = (($PageNumber - 1) * 25) + $ordinal
            source_record_id                        = $recordId
            name                                    = $name
            ex_name                                 = $cells["1"]
            imo_no                                  = $cells["12"]
            vessel_type                             = $cells["13"]
            ldt_metric_tonnes                       = $cells["14"]
            country_built                           = $cells["15"]
            built_year                              = $cells["16"]
            beached_date_source_text                = $cells["17"]
            propeller_shaft_diameter_unit_unspecified = $cells["49"]
        }
    }
}

function Get-AnalysisSeries {
    param([int]$Year)

    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $initial = Invoke-WebRequest -UseBasicParsing -WebSession $session -Uri $analysisUrl
    $html = $initial.Content

    if ($Year -ne $currentYear) {
        $form = Get-HiddenForm -Html $html
        $form["__EVENTTARGET"] = 'ctl00$ContentPlaceHolder1$ddl_Month'
        $form["__EVENTARGUMENT"] = ''
        $form['ctl00$ContentPlaceHolder1$ddl_Country'] = '101'
        $form['ctl00$ContentPlaceHolder1$ddl_Month'] = [string]$Year
        $form['ctl00$ContentPlaceHolder1$chk_Normal_Analysis$6'] = 'on'
        $form['ctl00$ContentPlaceHolder1$chk_Normal_Analysis$7'] = 'on'
        $response = Invoke-WebRequest -UseBasicParsing -WebSession $session -Method Post -Uri $analysisUrl -Body $form
        $html = $response.Content
    }

    $monthText = [regex]::Match(
        $html,
        'xAxis:.*?data:\s*\[(?<values>[^\]]*)\]',
        [Text.RegularExpressions.RegexOptions]::Singleline
    ).Groups["values"].Value
    $ldtText = [regex]::Match(
        $html,
        "name:\s*'Tons'.*?data:\s*\[(?<values>[^\]]*)\]",
        [Text.RegularExpressions.RegexOptions]::Singleline
    ).Groups["values"].Value
    $shipText = [regex]::Match(
        $html,
        "name:\s*'Ships'.*?data:\s*\[(?<values>[^\]]*)\]",
        [Text.RegularExpressions.RegexOptions]::Singleline
    ).Groups["values"].Value

    $months = @($monthText -split ',' | ForEach-Object { $_.Trim().Trim('"') })
    $ldt = @($ldtText -split ',' | ForEach-Object { [decimal]$_.Trim() })
    $ships = @($shipText -split ',' | ForEach-Object { [int]$_.Trim() })
    if (($months.Count -ne 12) -or ($ldt.Count -ne 12) -or ($ships.Count -ne 12)) {
        throw "Unexpected analysis series length for ${Year}: months=$($months.Count), LDT=$($ldt.Count), ships=$($ships.Count)"
    }

    for ($index = 0; $index -lt 12; $index += 1) {
        $monthNumber = $index + 1
        $period = "{0:D4}-{1:D2}" -f $Year, $monthNumber
        $status = "complete"
        if (($Year -eq $currentYear) -and ($monthNumber -eq $currentMonth)) {
            $status = "partial_at_acquisition"
        }
        elseif (($Year -eq $currentYear) -and ($monthNumber -gt $currentMonth)) {
            $status = "future_placeholder_zero"
        }

        [pscustomobject]@{
            acquired_at_utc   = $acquiredAtUtc
            source_url        = $analysisUrl
            period_month      = $period
            source_month_label = $months[$index]
            ldt_beached_metric_tonnes = $ldt[$index]
            ships_beached_count = $ships[$index]
            observation_status = $status
        }
    }
}

# Capture all three unauthenticated pages of the current demolition table.
$demolitionSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$page1 = Invoke-WebRequest -UseBasicParsing -WebSession $demolitionSession -Uri $demolitionUrl
$page2Form = Get-HiddenForm -Html $page1.Content
$page2Form["__EVENTTARGET"] = 'ctl00$ContentPlaceHolder1$RepeaterPaging$ctl01$Pagingbtn'
$page2Form["__EVENTARGUMENT"] = ''
$page2 = Invoke-WebRequest -UseBasicParsing -WebSession $demolitionSession -Method Post -Uri $demolitionUrl -Body $page2Form
$page3Form = Get-HiddenForm -Html $page2.Content
$page3Form["__EVENTTARGET"] = 'ctl00$ContentPlaceHolder1$RepeaterPaging$ctl02$Pagingbtn'
$page3Form["__EVENTARGUMENT"] = ''
$page3 = Invoke-WebRequest -UseBasicParsing -WebSession $demolitionSession -Method Post -Uri $demolitionUrl -Body $page3Form

$demolitionRows = @(
    ConvertFrom-DemolitionPage -Html $page1.Content -PageNumber 1
    ConvertFrom-DemolitionPage -Html $page2.Content -PageNumber 2
    ConvertFrom-DemolitionPage -Html $page3.Content -PageNumber 3
)
if ($demolitionRows.Count -ne 70) {
    throw "Expected 70 public demolition rows, captured $($demolitionRows.Count)."
}

$analysisRows = @()
foreach ($year in 2016..$currentYear) {
    $analysisRows += Get-AnalysisSeries -Year $year
}

$demolitionPath = Join-Path $OutputDirectory "alangtoday_demolition_current_${snapshotId}.csv"
$analysisPath = Join-Path $OutputDirectory "alangtoday_monthly_beachings_2016_${currentYear}_asof_${snapshotId}.csv"
$metadataPath = Join-Path $OutputDirectory "alangtoday_snapshot_${snapshotId}.metadata.json"

$demolitionRows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $demolitionPath
$analysisRows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $analysisPath

$metadata = [ordered]@{
    snapshot_id = $snapshotId
    acquired_at_utc = $acquiredAtUtc
    authentication_used = $false
    sources = @(
        [ordered]@{
            url = $demolitionUrl
            dataset = "Current India recycling table"
            captured_rows = $demolitionRows.Count
            captured_pages = 3
            scope = "Current-state snapshot rendered by the site; not a confirmed longitudinal event archive"
        },
        [ordered]@{
            url = $analysisUrl
            dataset = "Monthly LDT beached and number of ships beached"
            year_selector_confirmed = "2016-$currentYear"
            captured_rows = $analysisRows.Count
            scope = "Historical monthly values as rendered at acquisition; original release timestamps and revision history are unavailable"
        }
    )
    files = @(
        [ordered]@{
            path = $demolitionPath.Replace('\', '/')
            sha256 = (Get-FileHash -Algorithm SHA256 -Path $demolitionPath).Hash.ToLowerInvariant()
        },
        [ordered]@{
            path = $analysisPath.Replace('\', '/')
            sha256 = (Get-FileHash -Algorithm SHA256 -Path $analysisPath).Hash.ToLowerInvariant()
        }
    )
    caveats = @(
        "The demolition table reports 70 records at acquisition, including beaching dates from 2020 through 2026. It is a current-state table, not proof of a complete historical arrivals census.",
        "The monthly analysis history for 2016-$currentYear was confirmed through the public unauthenticated year selector, but past values may be revised and no point-in-time release archive was found.",
        "$($acquisitionInstant.ToString('MMMM yyyy')) is partial at acquisition; later months in $currentYear are future placeholders and must not be modeled as observations.",
        "AlangToday states that it takes no legal responsibility for the accuracy or completeness of its data.",
        "The site does not specify a unit for propeller shaft diameter on the public table; the field is retained only as source text."
    )
}
$metadata | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $metadataPath

[pscustomobject]@{
    acquired_at_utc = $acquiredAtUtc
    demolition_rows = $demolitionRows.Count
    analysis_rows = $analysisRows.Count
    demolition_file = $demolitionPath
    analysis_file = $analysisPath
    metadata_file = $metadataPath
} | ConvertTo-Json -Depth 3
