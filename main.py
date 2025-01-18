# Air quality application using the OpenAQ API.
import sys
import requests
import os
import pandas as pd
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import dash_daq as daq
import time
from requests.exceptions import RequestException
from dash import Dash, dcc, html, callback, Input, Output, ctx, State, no_update
from dash.exceptions import PreventUpdate
from dotenv import load_dotenv

# import pprint
# import tabulate

# Load environment variables.
load_dotenv()
API_KEY = os.getenv('OPENAQ_API_KEY')
ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
GITHUB = os.getenv('GITHUB')
LINKEDIN = os.getenv('LINKEDIN')

# URLs for making requests to the OpenAQ API.
URL_PM_DATA = 'https://api.openaq.org/v2/locations?limit=1000'
URL_RECENT_DATA = 'https://api.openaq.org/v2/measurements?'

REQUEST_HEADERS = {
    'X-API-KEY': API_KEY,
    'accept': 'application/json',
    'content-type': 'application/json'
}


def get_pm_data():
    """
    Retrieves data from all locations available with the OpenAQ API.

    :return:   Tuple containing a boolean indicating success or failure,
               and the location data if successful, or an error message if failed.
    """

    try:
        all_data = []
        page = 1

        # Fetch data from all available pages.
        while True:
            res = requests.get(f'{URL_PM_DATA}&page={page}', headers=REQUEST_HEADERS)
            if res.status_code == 200:
                page_data = res.json()
                if not page_data['results']:
                    break
                all_data.extend(page_data['results'])
                page += 1
            else:
                return False, f'Error getting pm data: {res.status_code}, {res.text}'

        df = pd.DataFrame(all_data)
        df = df.explode('parameters').reset_index(drop=True)

        # Filter data by pollutant type, excluding values outside the valid range.
        df_pm25 = df.loc[
            df['parameters'].apply(lambda parameters: parameters.get('parameter') if parameters else None) == 'pm25']
        df_pm25 = df_pm25.loc[df_pm25['parameters'].apply(
            lambda parameters: 0 <= parameters.get('lastValue') <= 350 if parameters else False)]

        df_pm10 = df.loc[
            df['parameters'].apply(lambda parameters: parameters.get('parameter') if parameters else None) == 'pm10']
        df_pm10 = df_pm10.loc[df_pm10['parameters'].apply(
            lambda parameters: 0 <= parameters.get('lastValue') <= 525 if parameters else False)]

        pm_data = [df_pm25, df_pm10]
        return True, pm_data

    except RequestException as e:
        return False, f'An error occurred while making the request: \n{e}'


def get_recent_data(location_id, pollutant):
    """
    Retrieves recent data for a single location from the OpenAQ API.

    :return:   Tuple containing a boolean indicating success or failure,
               and the location data if successful, or an error message if failed.
    """
    if pollutant == 'PM 2.5':
        pollutant = 'pm25'
        max_val = 350
    else:
        pollutant = 'pm10'
        max_val = 525

    # NOTE:
    #      The OpenAQ API may time out the connection if it has to search a wide date range.
    #      If they manage to fix this, change to query all data from first_updated to lats_updated.
    URL_WITH_PARAMS = (URL_RECENT_DATA + 'date_from=' + '2019-01-01' + 'T00%3A00%3A00Z' +
                       # '&date_to=' + last_updated +
                       '&limit=1000' +
                       '&location_id=' + location_id +
                       '&parameter=' + pollutant)

    try:
        time.sleep(1)  # Limits the API calls.
        res = requests.get(URL_WITH_PARAMS, headers=REQUEST_HEADERS)

        if res.status_code == 200:
            data = res.json()
            if not data['results']:
                return False, 'No data found for these parameters.'
            df = pd.DataFrame(data['results'])
            df['utc_date'] = df['date'].apply(lambda x: x['utc'])
            df = df.loc[df['value'].apply(lambda value: 0 <= value <= max_val if value else False)]
            return True, df
        else:
            return False, f'Error: {res.status_code}, {res.text}'

    except RequestException as e:
        return False, f'An error occurred while making the request: \n{e}'


def generate_map(data, pollutant, display_type):
    """
    Generates a Dash graphing_objects Figure containing a map.
    :param data: dataframe: Particulate matter data.
    :param pollutant: string: Pollutant type retrieved from the dropdown menu.
    :param display_type: string: Display type retrieved from the dropdown menu.

    :return: go.Figure: A Dash graphing_objects figure containing a Densitymapbox or a Scattermapbox.
    """
    # Data is attached to each marker to be used with callbacks and to set hover labels.
    data['name'] = data['name'].fillna('Name unavailable')
    custom_data = pd.DataFrame(
        {
            'id': data['id'],
            'name': data['name'],
            'city': data['city'],
            'country': data['country'],
            'last_value': data['parameters'].apply(lambda x: x['lastValue']),
            'last_updated': data['lastUpdated'].apply(lambda date: date.split('T')[0]),
            'first_updated': data['firstUpdated'].apply(lambda date: date.split('T')[0]),
            'last_update_time': data['lastUpdated'].apply(lambda date: date[11: 19]),
            'last_update_datetime': data['lastUpdated']
        }
    )

    # Set marker color based on last recorded concentration.
    values = data['parameters'].apply(lambda x: x['lastValue'])

    # Specific information from the data frame to display on map markers.
    hover_template = ('<b>%{customdata[1]}<br>'
                      '<br>'
                      f'{pollutant}:' ' %{customdata[4]} µg/m³<br>'
                      'Last Updated: %{customdata[5]} at %{customdata[7]} GMT<br>'
                      '<extra></extra>')

    # Apply appropriate color scale.
    if pollutant == 'PM 2.5':
        colorscale = [[0, 'green'],
                      [12.1 / 250, 'yellow'],
                      [35.5 / 250, 'orange'],
                      [55.5 / 250, 'red'],
                      [150.5 / 250, 'purple'],
                      [1, 'maroon']]

        tick_vals = [0, 12, 35, 55, 150, 250]
        color_scale_min = 0
        color_scale_max = 250
    else:
        colorscale = [[0, 'green'],
                      [55 / 425, 'yellow'],
                      [155 / 425, 'orange'],
                      [255 / 425, 'red'],
                      [355 / 425, 'purple'],
                      [1, 'maroon']]

        tick_vals = [0, 55, 155, 255, 355, 425]
        color_scale_min = 0
        color_scale_max = 425

    if display_type == 'Markers':
        # 'Markers' display generates a Scattermapbox.
        map_fig = go.Figure(go.Scattermapbox(
            mode='markers',
            marker=go.scattermapbox.Marker(size=20,
                                           color=values,
                                           colorscale=colorscale,
                                           colorbar=dict(
                                               title=dict(
                                                   text='Concentration (µg/m³)',
                                                   side='right',
                                                   font=dict(
                                                       color='white',
                                                       size=12
                                                   )
                                               ),
                                               bgcolor='rgba(0,0,0,0)',
                                               x=1.0,
                                               y=0.5,
                                               xanchor='right',
                                               yanchor='middle',
                                               len=0.5,
                                               thickness=20,
                                               tickvals=tick_vals,
                                               tickfont=dict(
                                                   color='white',
                                                   size=10
                                               ),
                                           ),
                                           cmin=color_scale_min,
                                           cmax=color_scale_max),
            lat=data['coordinates'].apply(lambda x: x['latitude']),
            lon=data['coordinates'].apply(lambda x: x['longitude']),
            customdata=custom_data)
        )

        # Apply mapbox styling.
        map_fig.update_layout(
            hovermode='closest',
            mapbox_style='carto-darkmatter',
            mapbox=dict(
                accesstoken=ACCESS_TOKEN,
                zoom=1,
                center=dict(
                    lat=17,
                    lon=17
                )
            ),
            margin=dict(
                l=0,
                r=0,
                b=0,
                t=0
            ),
            paper_bgcolor='rgba(0,0,0,0)'
        )

        # Set hover label options and apply marker clustering.
        map_fig.update_traces(hoverinfo='text',
                              hovertemplate=hover_template,
                              cluster=dict(
                                  enabled=True,
                                  color='lightblue',
                                  maxzoom=3
                              )
                              )

    elif display_type == 'Heatmap':
        # Markers display generates a Densitymapbox.
        map_fig = go.Figure(go.Densitymapbox(lat=data['coordinates'].apply(lambda x: x['latitude']),
                                             lon=data['coordinates'].apply(lambda x: x['longitude']),
                                             z=values,
                                             radius=20,
                                             colorscale=colorscale,
                                             colorbar=dict(
                                                 title=dict(
                                                     text='Concentration (µg/m³)',
                                                     side='right',
                                                     font=dict(
                                                         color='white',
                                                         size=12
                                                     )
                                                 ),
                                                 bgcolor='rgba(0,0,0,0)',
                                                 x=1.0,
                                                 y=0.5,
                                                 xanchor='right',
                                                 yanchor='middle',
                                                 len=0.5,
                                                 thickness=20,
                                                 tickfont=dict(
                                                     color='white',
                                                     size=10
                                                 ),
                                             ),
                                             zmin=color_scale_min,
                                             zmax=color_scale_max,
                                             hovertemplate=hover_template,
                                             customdata=custom_data
                                             ))

        # NOTE: Do NOT provide an access token for Densitymapbox. Doing so results in errors.
        map_fig.update_layout(
            mapbox_style='carto-darkmatter',
            mapbox=dict(
                zoom=1,
                center=dict(
                    lat=17,
                    lon=17
                )
            ),
            margin=dict(
                l=0,
                r=0,
                b=0,
                t=0
            )
        )

    return map_fig


def generate_graph(data, pollutant):
    """
    Generates a line plot of recent data from a specific location.

    :param data: dataframe: Recent data from a single location.
    :param pollutant: string: Pollutant type retrieved from the dropdown menu.

    :return: Dash go.Scatter: Scatter plot of recent pollutant readings.
    """
    location_name = data['location'].iloc[0]
    graph_title = location_name + f' - {pollutant}'
    dates = pd.Series(data['utc_date'])
    values = pd.Series(data['value'])
    graph_fig = go.Figure(go.Scatter(x=dates,
                                     y=values,
                                     line=dict(
                                         color='lightgreen')
                                     )
                          )
    graph_fig.update_layout(
        margin={'l': 40,
                'r': 40,
                'b': 40,
                't': 40},
        title=dict(
            text=graph_title,
            x=0.5,
            font=dict(
                color='white'
            )
        ),
        xaxis_title='Date',
        yaxis_title='Concentration (µg/m³)',
        xaxis=dict(
            title_font=dict(
                color='white'
            ),
            tickfont=dict(
                color='white'
            )
        ),
        yaxis=dict(
            title_font=dict(
                color='white'
            ),
            tickfont=dict(
                color='white'
            )
        ),
        plot_bgcolor='rgba(15, 15, 15, 1)',
        paper_bgcolor='rgba(45, 45, 45, 1)'
    )

    graph = dcc.Graph(id='recent-data-graph', figure=graph_fig, className='graph')

    return graph


def generate_table(data, pollutant):
    table_title = f'{pollutant}: All data'
    df = data[['id', 'name']].copy()
    df.loc[:, 'values'] = data['parameters'].apply(lambda x: x['lastValue'])
    df.loc[:, 'lastUpdated'] = data['lastUpdated'].apply(lambda x: f"{x.split('T')[0]} at {x[11: 19]} GMT")
    df.loc[:, 'coordinates'] = data['coordinates'].apply(lambda x: f"{x['latitude']}, {x['longitude']}")

    column_names = [
        {'headerName': 'ID', 'field': 'id'},
        {'headerName': 'Name', 'field': 'name', 'filter': True},
        {'headerName': f'Concentration (µg/m³)', 'field': 'values', 'filter': 'agNumberColumnFilter'},
        {'headerName': 'Last Updated', 'field': 'lastUpdated'},
        {'headerName': 'Coordinates (lat, long)', 'field': 'coordinates', 'hide': True},
    ]

    table = html.Div([
        html.H2(className='table-header', children=table_title),
        dag.AgGrid(
            id='data-table',
            rowData=df.to_dict('records'),
            dashGridOptions={
                'pagination': True,
                'rowSelection': 'single'
            },
            columnDefs=column_names,
            className="ag-theme-balham-dark",
            columnSize='responsiveSizeToFit'
        )]
    )

    return table


def get_default_graph(data, pollutant):
    """
    Generates the default graph which displays all data points for the specified pollutant.
    This graph is displayed before users click on a map marker or when data can not be retrieved from the API.
    :param data: dataframe: All data for the specified pollutant.
    :param pollutant: string: Pollutant type retrieved from the dropdown menu.

    :return: Dash graphing_objects Figure: A Dash Figure containing a Dash Scatter plot.
    """
    if data.empty:
        return
    graph_title = f'{pollutant}: All data'

    data['name'] = data['name'].fillna('Name unavailable')
    custom_data = pd.DataFrame(
        {
            'id': data['id'],
            'name': data['name'],
            'latitude': data['coordinates'].apply(lambda x: x['latitude']),
            'longitude': data['coordinates'].apply(lambda x: x['longitude'])
        }
    )

    graph_fig = go.Figure(go.Scatter(x=data['lastUpdated'].apply(lambda date: date.split('T')[0]),
                                     y=data['parameters'].apply(lambda x: x['lastValue']),
                                     mode='markers',
                                     marker=dict(
                                         color='lightgreen'
                                     ),
                                     customdata=custom_data,
                                     text=data['name']))

    graph_fig.update_layout(
        margin=dict(
            l=40,
            r=40,
            b=40,
            t=40
        ),
        title=dict(
            text=graph_title,
            x=0.5,
            font=dict(
                color='white'
            )
        ),
        xaxis_title='Date',
        yaxis_title='Concentration (µg/m³)',
        xaxis=dict(
            title_font=dict(
                color='white'
            ),
            tickfont=dict(
                color='white'
            )
        ),
        yaxis=dict(
            title_font=dict(
                color='white'
            ),
            tickfont=dict(
                color='white'
            )
        ),
        plot_bgcolor='rgba(15, 15, 15, 1)',
        paper_bgcolor='rgba(45, 45, 45, 1)'
    )

    graph = dcc.Graph(id='default-graph', figure=graph_fig, className='graph')

    return graph


def get_gauge_params(pollutant):
    """
    Returns the maximum concentration and color scale for analytics gauges.

    :param pollutant: string: Pollutant type retrieved from the dropdown menu.

    :return int, dict: Maximum value for the pollutant gauges, color gradient for the gauges.
    """
    if pollutant == 'PM 2.5':
        max_val = 250
        colors = dict(
            gradient=True,
            ranges={
                "green": [0, 12.1],
                "yellow": [12.1, 35.5],
                "orange": [35.5, 55.5],
                "red": [55.5, 150.5],
                "purple": [150.5, 250]
            }
        )
    else:
        max_val = 425
        colors = {
            'gradient': True,
            'ranges': {
                "green": [0, 55],
                "yellow": [55, 155],
                "orange": [155, 255],
                "red": [255, 355],
                "purple": [355, 425]
            }
        }

    return max_val, colors


def get_averages(data):
    """
    Gets the 24-hour and 7-day average pollutant reading for the specified location.
    :param data: dataframe: A dataframe containing recent data from a single location.

    :return: int, int: 24-hour average, 7-day average
    """
    dates = pd.to_datetime(data['utc_date'])
    most_recent_date = dates.max()

    last_24_hours = data[dates >= most_recent_date - pd.Timedelta(days=1)]
    last_7_days = data[dates >= most_recent_date - pd.Timedelta(days=7)]

    average_last_24_hours = last_24_hours['value'].mean()
    average_last_7_days = last_7_days['value'].mean()

    return average_last_24_hours, average_last_7_days


# Build app.
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, '/assets/styles.css'],
           suppress_callback_exceptions=True)
app.title = 'Global Air Quality Dashboard'

# Retrieve data from API.
success, response = get_pm_data()
pm25_data = []
pm10_data = []

if not success:
    print(response)
    sys.exit(1)
else:
    pm25_data = response[0]
    pm10_data = response[1]

DEFAULT_MAP_FIGURE = generate_map(pm25_data, 'PM 2.5', 'Markers')
DEFAULT_TABLE = generate_table(pm25_data, 'PM 2.5')

app.layout = html.Div([
    dcc.Store(id='pollutant-data-store'),
    html.H1(className='app-header', children='Global Air Quality Dashboard'),

    html.Div(className='upper-container',
             children=
             [
                 html.Div(
                     className='map-container',
                     children=
                     [
                         dcc.Loading(
                             dcc.Graph(
                                 id='map-figure',
                                 figure=DEFAULT_MAP_FIGURE,
                                 style={'height': '65vh'},
                                 config={'scrollZoom': True}
                             ),
                             delay_hide=300
                         ),
                         html.Div(className='map-options-container',
                                  children=
                                  [
                                      html.Div(
                                          className='map-option',
                                          children=[
                                              html.H3('Pollutant', className='dropdown-header'),
                                              dcc.Dropdown(id='pollutant-dropdown',
                                                           options=[{'label': 'PM 2.5', 'value': 'PM 2.5'},
                                                                    {'label': 'PM 10', 'value': 'PM 10'}
                                                                    ],
                                                           value='PM 2.5',
                                                           optionHeight=50,
                                                           maxHeight=100,
                                                           clearable=False)
                                          ]
                                      ),

                                      html.Div(
                                          className='map-option',
                                          children=[
                                              html.H3('Region Focus', className='dropdown-header'),
                                              dcc.Dropdown(id='region-dropdown',
                                                           options=[{'label': 'Show All',
                                                                     'value': 'Show All'},
                                                                    {'label': 'North America',
                                                                     'value': 'North America'},
                                                                    {'label': 'Central America',
                                                                     'value': 'Central America'},
                                                                    {'label': 'South America',
                                                                     'value': 'South America'},
                                                                    {'label': 'Europe',
                                                                     'value': 'Europe'},
                                                                    {'label': 'Africa',
                                                                     'value': 'Africa'},
                                                                    {'label': 'Asia',
                                                                     'value': 'Asia'},
                                                                    {'label': 'Oceania',
                                                                     'value': 'Oceania'}
                                                                    ],
                                                           value='Show All',
                                                           optionHeight=50,
                                                           maxHeight=100,
                                                           clearable=False)
                                          ]
                                      ),

                                      html.Div(
                                          className='map-option',
                                          children=[
                                              html.H3('Map Display', className='dropdown-header'),
                                              dcc.Dropdown(id='display-type-dropdown',
                                                           options=[{'label': 'Markers', 'value': 'Markers'},
                                                                    {'label': 'Density Heatmap', 'value': 'Heatmap'}
                                                                    ],
                                                           value='Markers',
                                                           optionHeight=50,
                                                           maxHeight=100,
                                                           clearable=False)
                                          ]
                                      )
                                  ]
                                  ),
                     ]
                 ),

                 html.Div(
                     className='analytics-container',
                     children=[
                         html.P(
                             'Click a marker on the map or a row on the table to show recent data from that location.'),
                         dcc.Loading(
                             html.Div(
                                 id='graph-figure',
                                 className='graph-container'
                             ),
                             delay_hide=300
                         ),
                         dbc.Alert(
                             className='missing-data-alert',
                             id='analytics-data-alert',
                             color='warning',
                             is_open=False,
                             dismissable=True,
                             duration=20000
                         ),
                         html.Div(
                             className='data-rep-container',
                             children=[
                                 daq.Gauge(
                                     id='pollutant-gauge-24hr',
                                     label='24 Hour Average (µg/m³)',
                                     labelPosition='bottom',
                                     min=0,
                                     max=250,
                                     showCurrentValue=True,
                                     value=0,
                                     size=150,
                                     color=dict(
                                         gradient=True,
                                         ranges={
                                             "green": [0, 12.1],
                                             "yellow": [12.1, 35.5],
                                             "orange": [35.5, 55.5],
                                             "red": [55.5, 150.5],
                                             "purple": [150.5, 250]
                                         }
                                     ),
                                     style={'display': 'block'}
                                 ),
                                 html.Div(daq.Gauge(
                                     id='pollutant-gauge-7day',
                                     label='7 Day Average (µg/m³)',
                                     labelPosition='bottom',
                                     min=0,
                                     max=250,
                                     showCurrentValue=True,
                                     value=0,
                                     size=150,
                                     color=dict(
                                         gradient=True,
                                         ranges={
                                             "green": [0, 12.1],
                                             "yellow": [12.1, 35.5],
                                             "orange": [35.5, 55.5],
                                             "red": [55.5, 150.5],
                                             "purple": [150.5, 250]
                                         }
                                     )
                                 ))
                             ]
                         )

                     ]
                 )
             ]
             ),
    html.Div(
        className='lower-container',
        children=[
            html.Div(
                id='datatable-container',
                className='datatable-container',
                children=[
                    DEFAULT_TABLE
                ]
            )
        ]
    ),
    html.Footer(
        className='app-footer',
        children=[
            html.Div('Created by Javon Jackson'),
            html.Div(
                className='external-links',
                children=[
                    html.A(
                        target='_blank',
                        href=GITHUB,
                        children=[
                            html.Img(
                                alt='Github Logo',
                                src='/assets/github-brands-solid.svg',
                            )
                        ]
                    ),
                    html.A(
                        target='_blank',
                        href=LINKEDIN,
                        children=[
                            html.Img(
                                alt='LinkedIn Logo',
                                src='/assets/linkedin-brands-solid.svg',
                            )
                        ]
                    )]
            )
        ]
    )
])


# Callback functions that update the Dash components.
@callback(
    Output('pollutant-data-store', 'data'),
    Input('pollutant-dropdown', 'value')
)
def update_pollutant_data(pollutant):
    if pollutant == 'PM 2.5':
        return pm25_data.to_dict('records')

    return pm10_data.to_dict('records')

@callback(
    Output('map-figure', 'figure', allow_duplicate=True),
    Output('graph-figure', 'children', allow_duplicate=True),
    Output('datatable-container', 'children'),
    Output('region-dropdown', 'value', allow_duplicate=True),
    Output('pollutant-gauge-24hr', 'max', allow_duplicate=True),
    Output('pollutant-gauge-7day', 'max', allow_duplicate=True),
    Output('pollutant-gauge-24hr', 'color', allow_duplicate=True),
    Output('pollutant-gauge-7day', 'color', allow_duplicate=True),
    Output('pollutant-gauge-24hr', 'value', allow_duplicate=True),
    Output('pollutant-gauge-7day', 'value', allow_duplicate=True),
    Input('pollutant-data-store', 'data'),
    State('pollutant-dropdown', 'value'),
    State('region-dropdown', 'value'),
    State('display-type-dropdown', 'value'),
    prevent_initial_call=True
)
def handle_data_update(data, pollutant, region, display_type):
    df = pd.DataFrame(data)
    map_fig = generate_map(df, pollutant, display_type)
    graph = get_default_graph(df, pollutant)
    table = generate_table(df, pollutant)
    gauge_max, gauge_colors = get_gauge_params(pollutant)

    return map_fig, graph, table, region, gauge_max, gauge_max, gauge_colors, gauge_colors, 0, 0

@callback(
    Output('map-figure', 'figure', allow_duplicate=True),
    Input('region-dropdown', 'value'),
    State('map-figure', 'figure'),
    prevent_initial_call=True
)
def region_focus(region, map_fig):
    coordinates = {
        'Show All': [17, 17, 1],
        'North America': [55.8457, -103.6386, 2],
        'South America': [-25.5, -61, 2.25],
        'Central America': [18, -90, 4],
        'Europe': [57, 16, 2],
        'Africa': [-1, 19.75, 2.3],
        'Asia': [28.33, 86.67, 2.3],
        'Oceania': [-31.55, 137.2, 2.3]
    }

    lat, lon, zoom = coordinates[region]
    map_fig = go.Figure(map_fig)
    map_fig.update_layout(mapbox=dict(center=dict(lat=lat, lon=lon)))
    map_fig.update_layout(mapbox=dict(zoom=zoom))

    return map_fig

@callback(
    Output('map-figure', 'figure', allow_duplicate=True),
    Output('region-dropdown', 'value'),
    State('pollutant-data-store', 'data'),
    State('pollutant-dropdown', 'value'),
    State('region-dropdown', 'value'),
    Input('display-type-dropdown', 'value'),
    prevent_initial_call=True
)
def update_map_type(data, pollutant, region, display_type):
    if not data:
        raise PreventUpdate
    df = pd.DataFrame(data)
    fig = generate_map(df, pollutant, display_type)

    return fig, region

@callback(
    Output('graph-figure', 'children', allow_duplicate=True),
    Output('pollutant-gauge-24hr', 'value', allow_duplicate=True),
    Output('pollutant-gauge-7day', 'value', allow_duplicate=True),
    Output('analytics-data-alert', 'children', allow_duplicate=True),
    Output('analytics-data-alert', 'is_open', allow_duplicate=True),
    Input('map-figure', 'clickData'),
    State('pollutant-dropdown', 'value'),
    State('pollutant-data-store', 'data'),
    prevent_initial_call=True
)
def handle_map_marker_click(click_data, pollutant, data):
    if not click_data:
        return no_update

    df = pd.DataFrame(click_data['points'])
    location_id = str(df['customdata'][0][0])
    location_name = df['customdata'][0][1]
    success, response = get_recent_data(location_id, pollutant)
    if success and not response.empty:
        graph = generate_graph(response, pollutant)
        avg_24hr, avg_7day = get_averages(response)
        return graph, avg_24hr, avg_7day, None, False
    else:
        all_data = pd.DataFrame(data)
        graph = get_default_graph(all_data, pollutant)
        if location_name:
            alert = f'Recent data for {location_name} is unavailable.'
        else:
            alert = 'Recent data is unavailable.'
        return graph, 0, 0, alert, True

@callback(
    Output('graph-figure', 'children', allow_duplicate=True),
    Output('map-figure', 'figure', allow_duplicate=True),
    Output('pollutant-gauge-24hr', 'value', allow_duplicate=True),
    Output('pollutant-gauge-7day', 'value', allow_duplicate=True),
    Output('analytics-data-alert', 'children', allow_duplicate=True),
    Output('analytics-data-alert', 'is_open', allow_duplicate=True),
    Input('data-table', 'selectedRows'),
    State('pollutant-dropdown', 'value'),
    State('pollutant-data-store', 'data'),
    State('map-figure', 'figure'),
    prevent_initial_call=True
)
def handle_table_click(selected_row, pollutant, data, map_fig):
    if not selected_row:
        return no_update
    else:
        location_id = str(selected_row[0]['id'])
        location_name = selected_row[0]['name']
        lat, lon = map(float, selected_row[0]['coordinates'].split(','))
        focused_map = go.Figure(map_fig)
        focused_map.update_layout(mapbox=dict(center=dict(lat=lat)))
        focused_map.update_layout(mapbox=dict(center=dict(lon=lon)))
        focused_map.update_layout(mapbox=dict(zoom=18))
        success, response = get_recent_data(location_id, pollutant)
        if success and not response.empty:
            graph = generate_graph(response, pollutant)
            avg_24hr, avg_7day = get_averages(response)
            return graph, focused_map, avg_24hr, avg_7day, None, False
        else:
            all_data = pd.DataFrame(data)
            graph = get_default_graph(all_data, pollutant)
            if location_name:
                alert = f'Recent data for {location_name} is unavailable.'
            else:
                alert = 'Recent data is unavailable.'
            return graph, focused_map, 0, 0, alert, True

@callback(
    Output('graph-figure', 'children', allow_duplicate=True),
    Output('map-figure', 'figure'),
    Output('pollutant-gauge-24hr', 'value', allow_duplicate=True),
    Output('pollutant-gauge-7day', 'value', allow_duplicate=True),
    Output('analytics-data-alert', 'children'),
    Output('analytics-data-alert', 'is_open'),
    Input('default-graph', 'clickData'),
    State('pollutant-dropdown', 'value'),
    State('pollutant-data-store', 'data'),
    State('map-figure', 'figure'),
    prevent_initial_call=True
)
def handle_default_graph_click(click_data, pollutant, data, map_fig):
    if not click_data:
        raise PreventUpdate

    location_id = str(click_data['points'][0]['customdata'][0])
    location_name = click_data['points'][0]['customdata'][1]
    lat = click_data['points'][0]['customdata'][2]
    lon = click_data['points'][0]['customdata'][3]
    focused_map = go.Figure(map_fig)
    focused_map.update_layout(mapbox=dict(center=dict(lat=lat)))
    focused_map.update_layout(mapbox=dict(center=dict(lon=lon)))
    focused_map.update_layout(mapbox=dict(zoom=18))
    success, response = get_recent_data(location_id, pollutant)
    if success and not response.empty:
        graph = generate_graph(response, pollutant)
        avg_24hr, avg_7day = get_averages(response)
        return graph, focused_map, avg_24hr, avg_7day, None, False
    else:
        all_data = pd.DataFrame(data)
        graph = get_default_graph(all_data, pollutant)
        if location_name:
            alert = f'Recent data for {location_name} is unavailable.'
        else:
            alert = 'Recent data is unavailable.'
        return graph, focused_map, 0, 0, alert, True


if __name__ == '__main__':
    app.run_server(debug=True)
